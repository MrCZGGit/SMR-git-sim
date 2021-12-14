#include <linux/device-mapper.h>
#include <linux/module.h>
#include <linux/init.h>
#include <linux/bio.h>
#include <linux/completion.h>
#include <linux/string_helpers.h>

#define DM_MSG_PREFIX "sadc"

/* Disk state reset IOCTL command. */
#define RESET_DISK 0xDEADBEEF

#define pbas_in_bio          bio_segments

#define bio_begin_lba(bio)   ((bio)->bi_sector)
#define bio_end_lba          bio_end_sector

#define bio_begin_pba(bio)   (lba_to_pba(bio_begin_lba(bio)))
#define bio_end_pba(bio)     (lba_to_pba(bio_end_lba(bio)))

#define MIN_DISK_SIZE (76LL << 10)
#define MAX_DISK_SIZE (10LL << 40)

#define LBA_SIZE 512
#define PBA_SIZE 4096
#define LBAS_IN_PBA (PBA_SIZE / LBA_SIZE)

#define lba_to_pba(lba) ((pba_t) (lba / LBAS_IN_PBA))
#define pba_to_lba(pba) (((lba_t) pba) * LBAS_IN_PBA)

typedef sector_t lba_t;
typedef int32_t pba_t;

#define MIN_IOS 16
#define MIN_POOL_PAGES 32

static struct kmem_cache *_io_pool;

struct io {
        struct sadc_ctx *sc;
        struct bio *bio;
        struct work_struct work;
        atomic_t pending;
};

struct cache_band {
        int32_t nr;
        pba_t begin_pba;
        pba_t current_pba;

        unsigned long *map;
};

struct sadc_ctx {
        struct dm_dev *dev;
        int64_t disk_size;

        int32_t cache_percent;

        int64_t cache_size;
        int32_t nr_cache_bands;
        int64_t usable_size;
        int64_t wasted_size;
        int32_t track_size;
        int64_t band_size;
        int32_t band_size_tracks;
        int32_t band_size_pbas;
        int32_t nr_valid_pbas;
        int32_t nr_usable_pbas;

        pba_t *pba_map;

        struct cache_band *cache_bands;

        int32_t nr_bands;
        int32_t nr_usable_bands;
        int32_t cache_assoc;

        mempool_t *io_pool;
        mempool_t *page_pool;
        struct workqueue_struct *queue;
        struct mutex lock;
        struct completion io_completion;
        struct bio_set *bs;
        atomic_t error;
        struct bio **tmp_bios;
        struct bio **rmw_bios;
};

static char *readable(u64 size)
{
        static char buf[10];

        string_get_size(size, STRING_UNITS_2, buf, sizeof(buf));

        return buf;
}

static inline void debug_bio(struct sadc_ctx *sc, struct bio *bio, const char *f)
{
        int i;
        unsigned long flags;
        struct bio_vec *bv;

        pr_debug("%10s: %c offset: %d size: %u\n",
                 f,
                 (bio_data_dir(bio) == READ ? 'R' : 'W'),
                 bio_begin_pba(bio),
                 bio->bi_size);

        bio_for_each_segment(bv, bio, i) {
                char *addr = bvec_kmap_irq(bv, &flags);
                pr_debug("seg: %d, addr: %p, len: %u, offset: %u, char: [%d]\n",
                         i, addr, bv->bv_len, bv->bv_offset, *addr);
                bvec_kunmap_irq(addr, &flags);
        }
}

static bool unaligned_bio(struct bio *bio)
{
        return bio_begin_lba(bio) & 0x7 || bio->bi_size & 0xfff;
}

static struct io *alloc_io(struct sadc_ctx *sc, struct bio *bio)
{
        struct io *io = mempool_alloc(sc->io_pool, GFP_NOIO);

        if (unlikely(!io)) {
                DMERR("Could not allocate io from mempool!");
                return NULL;
        }

        memset(io, 0, sizeof(*io));

        io->sc = sc;
        io->bio = bio;

        atomic_set(&io->pending, 0);

        return io;
}

static void sadcd(struct work_struct *work);

static void queue_io(struct io *io)
{
        struct sadc_ctx *sc = io->sc;

        INIT_WORK(&io->work, sadcd);
        queue_work(sc->queue, &io->work);
}

static void release_io(struct io *io, int error)
{
        struct sadc_ctx *sc = io->sc;
        bool rmw_bio = io->bio == NULL;

        WARN_ON(atomic_read(&io->pending));

        mempool_free(io, sc->io_pool);

        if (rmw_bio)
                atomic_set(&sc->error, error);
        else
                bio_endio(io->bio, error);
}

static inline bool usable_pba(struct sadc_ctx *sc, pba_t pba)
{
        return 0 <= pba && pba < sc->nr_usable_pbas;
}

static inline bool usable_band(struct sadc_ctx *sc, int32_t band)
{
        return 0 <= band && band < sc->nr_usable_bands;
}

static inline pba_t band_begin_pba(struct sadc_ctx *sc, int32_t band)
{
        WARN_ON(!usable_band(sc, band));

        return band * sc->band_size_pbas;
}

static inline pba_t band_end_pba(struct sadc_ctx *sc, int32_t band)
{
        return band_begin_pba(sc, band) + sc->band_size_pbas;
}

static inline int32_t pba_band(struct sadc_ctx *sc, pba_t pba)
{
        WARN_ON(!usable_pba(sc, pba));

        return pba / sc->band_size_pbas;
}

static inline int32_t bio_band(struct sadc_ctx *sc, struct bio *bio)
{
        return pba_band(sc, bio_begin_pba(bio));
}

static inline int band_to_bit(struct sadc_ctx *sc, struct cache_band *cb,
                              int32_t band)
{
        return (band - cb->nr) / sc->nr_cache_bands;
}

static inline int bit_to_band(struct sadc_ctx *sc, struct cache_band *cb,
                              int bit)
{
        return bit * sc->nr_cache_bands + cb->nr;
}

static inline struct cache_band *cache_band(struct sadc_ctx *sc, int32_t band)
{
        WARN_ON(!usable_band(sc, band));

        return &sc->cache_bands[band % sc->nr_cache_bands];
}

static inline int32_t free_pbas_in_cache_band(struct sadc_ctx *sc,
                                              struct cache_band *cb)
{
        return sc->band_size_pbas - (cb->current_pba - cb->begin_pba);
}

static int32_t pbas_in_band(struct sadc_ctx *sc, struct bio *bio, int32_t band)
{
        pba_t begin_pba = max(band_begin_pba(sc, band), bio_begin_pba(bio));
        pba_t end_pba = min(band_end_pba(sc, band), bio_end_pba(bio));

        return max(end_pba - begin_pba, 0);
}

static void unmap_pba_range(struct sadc_ctx *sc, pba_t begin, pba_t end)
{
        int i;

        WARN_ON(begin >= end);
        WARN_ON(!usable_pba(sc, end - 1));

        for (i = begin; i < end; ++i)
                sc->pba_map[i] = -1;
}

static pba_t map_pba_range(struct sadc_ctx *sc, pba_t begin, pba_t end)
{
        pba_t i;
        int32_t b;
        struct cache_band *cb;

        WARN_ON(begin >= end);
        WARN_ON(!usable_pba(sc, end - 1));

        b = pba_band(sc, begin);

        WARN_ON(b != pba_band(sc, end - 1));

        cb = cache_band(sc, b);

        WARN_ON(free_pbas_in_cache_band(sc, cb) < (end - begin));

        for (i = begin; i < end; ++i)
                sc->pba_map[i] = cb->current_pba++;

        set_bit(band_to_bit(sc, cb, b), cb->map);

        return sc->pba_map[begin];
}

static inline pba_t lookup_pba(struct sadc_ctx *sc, pba_t pba)
{
        WARN_ON(!usable_pba(sc, pba));

        return sc->pba_map[pba] == -1 ? pba : sc->pba_map[pba];
}

static inline lba_t lookup_lba(struct sadc_ctx *sc, lba_t lba)
{
        return pba_to_lba(lookup_pba(sc, lba_to_pba(lba))) + lba % LBAS_IN_PBA;
}

static void do_free_bio_pages(struct sadc_ctx *sc, struct bio *bio)
{
        int i;
        struct bio_vec *bv;

        bio_for_each_segment_all(bv, bio, i) {
                WARN_ON(!bv->bv_page);
                mempool_free(bv->bv_page, sc->page_pool);
                bv->bv_page = NULL;
        }

        /* For now we should only have a single page per bio. */
        WARN_ON(i != 1);
}

static void endio(struct bio *bio, int error)
{
        struct io *io = bio->bi_private;
        struct sadc_ctx *sc = io->sc;
        bool rmw_bio = io->bio == NULL;

        if (rmw_bio && bio_data_dir(bio) == WRITE)
                do_free_bio_pages(sc, bio);

        bio_put(bio);

        if (atomic_dec_and_test(&io->pending)) {
                release_io(io, error);
                complete(&sc->io_completion);
        }
}

static bool adjacent_pbas(struct sadc_ctx *sc, pba_t x, pba_t y)
{
        return lookup_pba(sc, x) + 1 == lookup_pba(sc, y);
}

static struct bio *clone_remap_bio(struct io *io, struct bio *bio, int idx,
                                   pba_t pba, int nr_pbas)
{
        struct sadc_ctx *sc = io->sc;
        struct bio *clone;

        clone = bio_clone_bioset(bio, GFP_NOIO, sc->bs);
        if (unlikely(!clone)) {
                DMERR("Cannot clone a bio.");
                return NULL;
        }

        if (bio_data_dir(bio) == READ)
                pba = lookup_pba(sc, pba);
        else
                pba = map_pba_range(sc, pba, pba + nr_pbas);

        clone->bi_sector = pba_to_lba(pba);
        clone->bi_private = io;
        clone->bi_end_io = endio;
        clone->bi_bdev = sc->dev->bdev;

        clone->bi_idx = idx;
        clone->bi_vcnt = idx + nr_pbas;
        clone->bi_size = nr_pbas * PBA_SIZE;

        atomic_inc(&io->pending);

        return clone;
}

static void release_bio(struct bio *bio)
{
        struct io *io = bio->bi_private;

        atomic_dec(&io->pending);
        bio_put(bio);
}

static int handle_unaligned_io(struct sadc_ctx *sc, struct io *io)
{
        struct bio *bio = io->bio;
        struct bio *clone = bio_clone_bioset(bio, GFP_NOIO, sc->bs);

        WARN_ON(bio_data_dir(bio) != READ);
        WARN_ON(bio_end_lba(bio) > pba_to_lba(bio_begin_pba(bio) + 1));

        if (unlikely(!clone)) {
                DMERR("Cannot clone a bio.");
                return -ENOMEM;
        }

        clone->bi_sector = lookup_lba(sc, bio_begin_lba(bio));
        clone->bi_private = io;
        clone->bi_end_io = endio;
        clone->bi_bdev = sc->dev->bdev;

        atomic_inc(&io->pending);

        sc->tmp_bios[0] = clone;

        return 1;
}

static int split_read_io(struct sadc_ctx *sc, struct io *io)
{
        struct bio *bio = io->bio;
        pba_t bp, p;
        int i, n = 0, idx = 0;

        if (unlikely(unaligned_bio(bio)))
                return handle_unaligned_io(sc, io);

        bp = bio_begin_pba(bio);
        p = bp + 1;

        for (i = 1; p < bio_end_pba(bio); ++i, ++p) {
                if (adjacent_pbas(sc, p - 1, p))
                        continue;
                sc->tmp_bios[n] = clone_remap_bio(io, bio, idx, bp, i - idx);
                if (!sc->tmp_bios[n])
                        goto bad;
                ++n, idx = i, bp = p;
        }

        sc->tmp_bios[n] = clone_remap_bio(io, bio, idx, bp, i - idx);
        if (sc->tmp_bios[n])
                return n + 1;

bad:
        while (n--)
                release_bio(sc->tmp_bios[n]);
        return -ENOMEM;
}

static int split_write_io(struct sadc_ctx *sc, struct io *io)
{
        struct bio *bio = io->bio;
        int32_t nr_pbas_bio1, nr_pbas_bio2;
        int idx = 0;
        pba_t p;

        nr_pbas_bio1 = pbas_in_band(sc, bio, bio_band(sc, bio));
        nr_pbas_bio2 = pbas_in_bio(bio) - nr_pbas_bio1;
        p = bio_begin_pba(bio);

        sc->tmp_bios[0] = clone_remap_bio(io, bio, idx, p, nr_pbas_bio1);
        if (!sc->tmp_bios[0])
                return -ENOMEM;

        if (!nr_pbas_bio2)
                return 1;

        p += nr_pbas_bio1;
        idx += nr_pbas_bio1;

        sc->tmp_bios[1] =
                clone_remap_bio(io, bio, idx, p, nr_pbas_bio2);
        if (!sc->tmp_bios[1]) {
                release_bio(sc->tmp_bios[0]);
                return -ENOMEM;
        }

        return 2;
}

static int do_sync_io(struct sadc_ctx *sc, struct bio **bios, int n)
{
        int i;

        reinit_completion(&sc->io_completion);

        for (i = 0; i < n; ++i)
                generic_make_request(bios[i]);

        wait_for_completion(&sc->io_completion);

        return atomic_read(&sc->error);
}

typedef int (*split_t)(struct sadc_ctx *sc, struct io *io);

static void do_io(struct sadc_ctx *sc, struct io *io, split_t split)
{
        int n = split(sc, io);

        if (n < 0) {
                release_io(io, n);
                return;
        }

        WARN_ON(!n);

        do_sync_io(sc, sc->tmp_bios, n);
}

static struct cache_band *cache_band_to_gc(struct sadc_ctx *sc, struct bio *bio)
{
        int b = bio_band(sc, bio);
        int nr_pbas = pbas_in_band(sc, bio, b);
        struct cache_band *cb = cache_band(sc, b);

        if (free_pbas_in_cache_band(sc, cb) < nr_pbas)
                return cb;

        if (!usable_band(sc, ++b))
                return NULL;

        cb = cache_band(sc, b);
        nr_pbas = pbas_in_bio(bio) - nr_pbas;

        return free_pbas_in_cache_band(sc, cb) < nr_pbas ? cb : NULL;
}

static struct bio *alloc_bio_with_page(struct sadc_ctx *sc, pba_t pba)
{
        struct page *page = mempool_alloc(sc->page_pool, GFP_NOIO);
        struct bio *bio = bio_alloc_bioset(GFP_NOIO, 1, sc->bs);

        if (!bio || !page)
                goto bad;

        bio->bi_sector = pba_to_lba(pba);
        bio->bi_bdev = sc->dev->bdev;

        if (!bio_add_page(bio, page, PAGE_SIZE, 0))
                goto bad;

        return bio;

bad:
        if (page)
                mempool_free(page, sc->page_pool);
        if (bio)
                bio_put(bio);
        return NULL;
}

static void free_rmw_bios(struct sadc_ctx *sc, int n)
{
        int i;

        for (i = 0; i < n; ++i) {
                do_free_bio_pages(sc, sc->rmw_bios[i]);
                bio_put(sc->rmw_bios[i]);
        }
}

static bool alloc_rmw_bios(struct sadc_ctx *sc, int32_t band)
{
        pba_t p = band_begin_pba(sc, band);
        int i;

        for (i = 0; i < sc->band_size_pbas; ++i) {
                sc->rmw_bios[i] = alloc_bio_with_page(sc, p + i);
                if (!sc->rmw_bios[i])
                        goto bad;
        }
        return true;

bad:
        free_rmw_bios(sc, i);
        return false;
}

static struct bio *clone_bio(struct io *io, struct bio *bio, pba_t pba)
{
        struct sadc_ctx *sc = io->sc;
        struct bio *clone = bio_clone_bioset(bio, GFP_NOIO, sc->bs);

        if (unlikely(!clone)) {
                DMERR("Cannot clone bio.");
                return NULL;
        }

        clone->bi_private = io;
        clone->bi_end_io = endio;
        clone->bi_sector = pba_to_lba(pba);

        atomic_inc(&io->pending);

        return clone;
}

static int do_read_band(struct sadc_ctx *sc, int32_t band)
{
        struct io *io = alloc_io(sc, NULL);
        pba_t p = band_begin_pba(sc, band);
        int i;

        if (unlikely(!io))
                return -ENOMEM;

        for (i = 0; i < sc->band_size_pbas; ++i) {
                sc->tmp_bios[i] = clone_bio(io, sc->rmw_bios[i], p + i);
                if (!sc->tmp_bios[i])
                        goto bad;
        }

        return do_sync_io(sc, sc->tmp_bios, sc->band_size_pbas);

bad:
        while (i--)
                release_bio(sc->tmp_bios[i]);
        return -ENOMEM;
}

static int do_modify_band(struct sadc_ctx *sc, int32_t band)
{
        struct io *io = alloc_io(sc, NULL);
        pba_t p = band_begin_pba(sc, band);
        int i, j;

        if (unlikely(!io))
                return -ENOMEM;

        for (i = j = 0; i < sc->band_size_pbas; ++i) {
                pba_t pp = lookup_pba(sc, bio_begin_pba(sc->rmw_bios[i]));

                if (pp == p + i)
                        continue;

                sc->tmp_bios[j] = clone_bio(io, sc->rmw_bios[i], pp);
                if (!sc->tmp_bios[j])
                        goto bad;
                ++j;
        }

        WARN_ON(!j);

        return do_sync_io(sc, sc->tmp_bios, j);

bad:
        while (j--)
                release_bio(sc->tmp_bios[j]);
        return -ENOMEM;
}

static int do_write_band(struct sadc_ctx *sc, int32_t band)
{
        struct io *io = alloc_io(sc, NULL);
        int i;

        if (unlikely(!io))
                return -ENOMEM;

        for (i = 0; i < sc->band_size_pbas; ++i) {
                sc->rmw_bios[i]->bi_private = io;
                sc->rmw_bios[i]->bi_end_io = endio;
                sc->rmw_bios[i]->bi_rw = WRITE;
        }

        atomic_set(&io->pending, sc->band_size_pbas);

        return do_sync_io(sc, sc->rmw_bios, sc->band_size_pbas);
}

static int do_rmw_band(struct sadc_ctx *sc, int32_t band)
{
        int r = 0;

        if (!alloc_rmw_bios(sc, band))
                return -ENOMEM;

        pr_debug("Reading band %d\n", band);
        r = do_read_band(sc, band);
        if (r < 0)
                goto bad;

        pr_debug("Modifying band %d\n", band);
        r = do_modify_band(sc, band);
        if (r < 0)
                goto bad;

        pr_debug("Writing band %d\n", band);
        return do_write_band(sc, band);

bad:
        free_rmw_bios(sc, sc->band_size_pbas);
        return r;
}

static void reset_cache_band(struct sadc_ctx *sc, struct cache_band *cb)
{
        cb->current_pba = cb->begin_pba;
        bitmap_zero(cb->map, sc->cache_assoc);
}

static int do_gc_cache_band(struct sadc_ctx *sc, struct cache_band *cb)
{
        int i;

        for_each_set_bit(i, cb->map, sc->cache_assoc) {
                int b = bit_to_band(sc, cb, i);
                int r = do_rmw_band(sc, b);
                if (r < 0)
                        return r;
                unmap_pba_range(sc, band_begin_pba(sc, b), band_end_pba(sc, b));
        }
        reset_cache_band(sc, cb);
        return 0;
}

static int do_gc_if_required(struct sadc_ctx *sc, struct bio *bio)
{
        struct cache_band *cb = cache_band_to_gc(sc, bio);
        int r = 0;

        if (!cb)
                return r;

        pr_debug("%d Starting GC.\n", current->pid);
        do {
                r = do_gc_cache_band(sc, cb);
                if (r < 0)
                        return r;
                cb = cache_band_to_gc(sc, bio);
        } while (cb);

        pr_debug("%d GC completed.\n", current->pid);
        return r;
}

static void sadcd(struct work_struct *work)
{
        struct io *io = container_of(work, struct io, work);
        struct sadc_ctx *sc = io->sc;
        struct bio *bio = io->bio;

        mutex_lock(&sc->lock);

        if (bio_data_dir(bio) == READ) {
                do_io(sc, io, split_read_io);
        } else {
                int r;

                WARN_ON(unaligned_bio(bio));

                r = do_gc_if_required(sc, bio);
                if (r < 0)
                        release_io(io, r);
                else
                        do_io(sc, io, split_write_io);
        }

        mutex_unlock(&sc->lock);
}

static bool get_args(struct dm_target *ti, struct sadc_ctx *sc,
                     int argc, char **argv)
{
        unsigned long long tmp;
        char d;

        if (argc != 5) {
                ti->error = "dm-sadc: Invalid argument count.";
                return false;
        }

        if (sscanf(argv[1], "%llu%c", &tmp, &d) != 1 || tmp & 0xfff ||
            (tmp < 4 * 1024 || tmp > 2 * 1024 * 1024)) {
                ti->error = "dm-sadc: Invalid track size.";
                return false;
        }
        sc->track_size = tmp;

        if (sscanf(argv[2], "%llu%c", &tmp, &d) != 1 || tmp < 1 || tmp > 200) {
                ti->error = "dm-sadc: Invalid band size.";
                return false;
        }
        sc->band_size_tracks = tmp;

        if (sscanf(argv[3], "%llu%c", &tmp, &d) != 1 || tmp < 1 || tmp > 50) {
                ti->error = "dm-sadc: Invalid cache percent.";
                return false;
        }
        sc->cache_percent = tmp;

        if (sscanf(argv[4], "%llu%c", &tmp, &d) != 1 ||
            tmp < MIN_DISK_SIZE || tmp > MAX_DISK_SIZE) {
                ti->error = "dm-sadc: Invalid disk size.";
                return false;
        }
        sc->disk_size = tmp;

        return true;
}

static void calc_params(struct sadc_ctx *sc)
{
        sc->band_size      = sc->band_size_tracks * sc->track_size;
        sc->band_size_pbas = sc->band_size / PBA_SIZE;
        sc->nr_bands       = sc->disk_size / sc->band_size;
        sc->nr_cache_bands = sc->nr_bands * sc->cache_percent / 100;
        sc->cache_size     = sc->nr_cache_bands * sc->band_size;

        /*
         * Make |nr_usable_bands| a multiple of |nr_cache_bands| so that all
         * cache bands are equally loaded.
         */
        sc->nr_usable_bands  = (sc->nr_bands / sc->nr_cache_bands - 1) *
                sc->nr_cache_bands;

        sc->cache_assoc    = sc->nr_usable_bands / sc->nr_cache_bands;
        sc->usable_size    = sc->nr_usable_bands * sc->band_size;
        sc->wasted_size    = sc->disk_size - sc->cache_size - sc->usable_size;
        sc->nr_valid_pbas  = (sc->usable_size + sc->cache_size) / PBA_SIZE;
        sc->nr_usable_pbas = sc->usable_size / PBA_SIZE;

        WARN_ON(sc->usable_size % PBA_SIZE);
}

static void print_params(struct sadc_ctx *sc)
{
        DMINFO("Disk size: %s",              readable(sc->disk_size));
        DMINFO("Band size: %s",              readable(sc->band_size));
        DMINFO("Band size: %d pbas",         sc->band_size_pbas);
        DMINFO("Total number of bands: %d",  sc->nr_bands);
        DMINFO("Number of cache bands: %d",  sc->nr_cache_bands);
        DMINFO("Cache size: %s",             readable(sc->cache_size));
        DMINFO("Number of usable bands: %d", sc->nr_usable_bands);
        DMINFO("Usable disk size: %s",       readable(sc->usable_size));
        DMINFO("Number of usable pbas: %d",  sc->nr_usable_pbas);
        DMINFO("Wasted disk size: %s",       readable(sc->wasted_size));
}

static void sadc_dtr(struct dm_target *ti)
{
        int i;
        struct sadc_ctx *sc = (struct sadc_ctx *) ti->private;

        DMINFO("Destructing...");

        ti->private = NULL;

        if (!sc)
                return;

        if (sc->tmp_bios)
                vfree(sc->tmp_bios);
        if (sc->rmw_bios)
                vfree(sc->rmw_bios);
        if (sc->pba_map)
                vfree(sc->pba_map);

        for (i = 0; i < sc->nr_cache_bands; ++i)
                if (sc->cache_bands[i].map)
                        kfree(sc->cache_bands[i].map);

        if (sc->cache_bands)
                vfree(sc->cache_bands);

        if (sc->io_pool)
                mempool_destroy(sc->io_pool);
        if (sc->queue)
                destroy_workqueue(sc->queue);
        if (sc->dev)
                dm_put_device(ti, sc->dev);
        kzfree(sc);
}

static bool alloc_structs(struct sadc_ctx *sc)
{
        int32_t i, size, pba;

        size = sizeof(int32_t) * sc->nr_usable_pbas;
        sc->pba_map = vmalloc(size);
        if (!sc->pba_map)
                return false;
        memset(sc->pba_map, -1, size);

        size = sizeof(struct bio *) * sc->band_size_pbas;
        sc->rmw_bios = vzalloc(size);
        if (!sc->rmw_bios)
                return false;

        sc->tmp_bios = vzalloc(size);
        if (!sc->tmp_bios)
                return false;

        size = sizeof(struct cache_band) * sc->nr_cache_bands;
        sc->cache_bands = vmalloc(size);
        if (!sc->cache_bands)
                return false;

        /* The cache region starts where the data region ends. */
        pba = sc->nr_usable_pbas;

        size = BITS_TO_LONGS(sc->cache_assoc) * sizeof(long);
        for (i = 0; i < sc->nr_cache_bands; ++i, pba += sc->band_size_pbas) {
                sc->cache_bands[i].nr = i;
                sc->cache_bands[i].begin_pba = pba;
                sc->cache_bands[i].map = kmalloc(size, GFP_KERNEL);
                if (!sc->cache_bands[i].map)
                        return false;
                reset_cache_band(sc, &sc->cache_bands[i]);
        }

        return true;
}

static int sadc_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
        struct sadc_ctx *sc;
        int32_t ret;

        DMINFO("Constructing...");

        sc = kzalloc(sizeof(*sc), GFP_KERNEL);
        if (!sc) {
                ti->error = "dm-sadc: Cannot allocate sadc context.";
                return -ENOMEM;
        }
        ti->private = sc;

        if (!get_args(ti, sc, argc, argv)) {
                kzfree(sc);
                return -EINVAL;
        }

        calc_params(sc);
        print_params(sc);

        ret = -ENOMEM;
        if (!alloc_structs(sc)) {
                ti->error = "Cannot allocate data structures.";
                goto bad;
        }

        sc->io_pool = mempool_create_slab_pool(MIN_IOS, _io_pool);
        if (!sc->io_pool) {
                ti->error = "Cannot allocate mempool.";
                goto bad;
        }

        sc->page_pool = mempool_create_page_pool(MIN_POOL_PAGES, 0);
        if (!sc->page_pool) {
                ti->error = "Cannot allocate page mempool.";
                goto bad;
        }

        sc->bs = bioset_create(MIN_IOS, 0);
        if (!sc->bs) {
                ti->error = "Cannot allocate bioset.";
                goto bad;
        }

        sc->queue = alloc_workqueue("sadcd",
                                    WQ_NON_REENTRANT | WQ_MEM_RECLAIM, 1);
        if (!sc->queue) {
                ti->error = "Cannot allocate work queue.";
                goto bad;
        }

        ret = -EINVAL;
        if (dm_get_device(ti, argv[0], dm_table_get_mode(ti->table), &sc->dev)) {
                ti->error = "dm-sadc: Device lookup failed.";
                return -1;
        }

        mutex_init(&sc->lock);
        init_completion(&sc->io_completion);

        /* TODO: Reconsider proper values for these. */
        ti->num_flush_bios = 1;
        ti->num_discard_bios = 1;
        ti->num_write_same_bios = 1;

        return 0;

bad:
        sadc_dtr(ti);
        return ret;
}

static int sadc_map(struct dm_target *ti, struct bio *bio)
{
        struct sadc_ctx *sc = ti->private;
        struct io *io;

        if (unlikely(bio->bi_rw & (REQ_FLUSH | REQ_DISCARD))) {
                WARN_ON(bio_sectors(bio));
                bio->bi_bdev = sc->dev->bdev;
                return DM_MAPIO_REMAPPED;
        }

        io = alloc_io(sc, bio);
        if (unlikely(!io))
                return -EIO;

        queue_io(io);

        return DM_MAPIO_SUBMITTED;
}

static void sadc_status(struct dm_target *ti, status_type_t type,
                        unsigned status_flags, char *result, unsigned maxlen)
{
        struct sadc_ctx *sc = (struct sadc_ctx *) ti->private;

        switch (type) {
        case STATUSTYPE_INFO:
                result[0] = '\0';
                break;

        /* TODO: get string representation of device name.*/
        case STATUSTYPE_TABLE:
                snprintf(result, maxlen, "%s track size: %d, band size in tracks: %d, cache percent: %d%%",
                         sc->dev->name,
                         sc->track_size,
                         sc->band_size_tracks,
                         sc->cache_percent);
                break;
        }
}

static int reset_disk(struct sadc_ctx *sc)
{
        int i;

        DMINFO("Resetting disk...");

        if (!mutex_trylock(&sc->lock)) {
                DMINFO("Cannot reset -- GC in progres...");
                return -EIO;
        }

        for (i = 0; i < sc->nr_cache_bands; ++i)
                reset_cache_band(sc, &sc->cache_bands[i]);

        memset(sc->pba_map, -1, sizeof(pba_t) * sc->nr_usable_pbas);

        mutex_unlock(&sc->lock);

        return 0;
}

static int sadc_ioctl(struct dm_target *ti, unsigned int cmd, unsigned long arg)
{
        struct sadc_ctx *sc = ti->private;

        if (cmd == RESET_DISK)
                return reset_disk(sc);
        return -EINVAL;
}

static int sadc_iterate_devices(struct dm_target *ti,
                                iterate_devices_callout_fn fn, void *data)
{
        struct sadc_ctx *sc = ti->private;

        return fn(ti, sc->dev, 0, ti->len, data);
}

static struct target_type sadc_target = {
        .name            = "sadc",
        .version         = {1, 0, 0},
        .module          = THIS_MODULE,
        .ctr             = sadc_ctr,
        .dtr             = sadc_dtr,
        .map             = sadc_map,
        .status          = sadc_status,
        .ioctl           = sadc_ioctl,
        .iterate_devices = sadc_iterate_devices,
};

static int __init sadc_init(void)
{
        int r;

        _io_pool = KMEM_CACHE(io, 0);
        if (!_io_pool)
                return -ENOMEM;

        r = dm_register_target(&sadc_target);
        if (r < 0) {
                DMERR("register failed %d", r);
                kmem_cache_destroy(_io_pool);
        }

        return r;
}



static void __exit sadc_exit(void)
{
        dm_unregister_target(&sadc_target);
}

module_init(sadc_init);
module_exit(sadc_exit);

MODULE_DESCRIPTION(DM_NAME " set-associative disk cache STL emulator target");
MODULE_LICENSE("GPL");
