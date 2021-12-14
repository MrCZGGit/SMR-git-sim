#include <linux/bio.h>
#include <linux/workqueue.h>
#include <linux/slab.h>
#include <linux/blkdev.h>
#include <linux/device-mapper.h>
#include <linux/init.h>
#include <linux/mempool.h>
#include <linux/module.h>
#include <linux/slab.h>

#define DM_MSG_PREFIX "passthru"

/*
 * Passthru: A passthrough target that performs reads and writes via a
 * workqueue.
 */
struct passthru_c {
        struct dm_dev *dev;
        mempool_t *io_pool;         /* For per bio private data. */
        struct bio_set *bs;         /* For cloned bios. */
  
        struct workqueue_struct *io_queue;
};

struct passthru_io {
        struct passthru_c *pc;
        struct bio *base_bio;
        struct work_struct work;
        int error;
        atomic_t io_pending;
};

#define MIN_IOS        16
#define MIN_POOL_PAGES 32

static struct kmem_cache *_passthru_io_pool;


static void passthru_dtr(struct dm_target *ti)
{
        struct passthru_c *pc = (struct passthru_c *) ti->private;

        DMERR("Passthru: destructing...");
        ti->private = NULL;
        if (!pc)
                return;

        if (pc->io_queue)
                destroy_workqueue(pc->io_queue);
        if (pc->bs)
                bioset_free(pc->bs);
        if (pc->io_pool)
                mempool_destroy(pc->io_pool);
        if (pc->dev)
                dm_put_device(ti, pc->dev);
        kfree(pc);
}

/*
 * Construct a passthru mapping: <dev_path>
 */
static int passthru_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
        struct passthru_c *pc;
        int ret;

        DMERR("Passthru: constructing...");
        if (argc != 1) {
                ti->error = "Invalid argument count";
                return -EINVAL;
        }

        pc = kmalloc(sizeof(*pc), GFP_KERNEL);
        if (!pc) {
                ti->error = "dm-passthru: Cannot allocate passthru context";
                return -ENOMEM;
        }
        ti->private = pc;

        ret = -ENOMEM;
        pc->io_pool = mempool_create_slab_pool(MIN_IOS, _passthru_io_pool);
        if (!pc->io_pool) {
                ti->error = "Cannot allocate passthru io mempool";
                goto bad;
        }

        pc->bs = bioset_create(MIN_IOS, 0);
        if (!pc->bs) {
                ti->error = "Cannot allocate crypt bioset";
                goto bad;
        }

        pc->io_queue = alloc_workqueue("passthrud_io",
                                       WQ_NON_REENTRANT|WQ_MEM_RECLAIM,
                                       1);
        if (!pc->io_queue) {
                ti->error = "Cannot allocated passthrud io queue";
                goto bad;
        }
  
        ret = -EINVAL;
        if (dm_get_device(ti, argv[0], dm_table_get_mode(ti->table), &pc->dev)) {
                ti->error = "dm-passthru: Device lookup failed";
                goto bad;
        }

        ti->num_flush_bios = 1;
        ti->num_discard_bios = 1;
        ti->num_write_same_bios = 1;
        return 0;

bad:
        passthru_dtr(ti);
        return ret;
}

static struct passthru_io *passthru_io_alloc(struct passthru_c *pc,
                                             struct bio *bio)
{
        struct passthru_io *io;

        io = mempool_alloc(pc->io_pool, GFP_NOIO);
        io->pc = pc;
        io->base_bio = bio;
        io->error = 0;
        atomic_set(&io->io_pending, 1);
  
        return io;
}

static void passthru_io_release(struct passthru_io *io)
{
        struct passthru_c *pc = io->pc;
        struct bio *base_bio = io->base_bio;
        int error = io->error;

        BUG_ON(!atomic_dec_and_test(io->io_pending));
        mempool_free(io, pc->io_pool);
        bio_endio(base_bio, error);
}

static void passthru_endio(struct bio *clone, int error)
{
        struct passthru_io *io = clone->bi_private;

        if (unlikely(!bio_flagged(clone, BIO_UPTODATE) && !error))
                io->error = -EIO;

        DMERR("%s %c %lu",
              (io->error ? "!!" : "OK"),
              (bio_data_dir(clone) == READ ? 'R' : 'W'),
              clone->bi_sector);
  
        bio_put(clone);
        passthru_io_release(io);
}

static void clone_init(struct passthru_io *io, struct bio *clone)
{
        struct passthru_c *pc = io->pc;

        clone->bi_private = io;
        clone->bi_end_io = passthru_endio;
        clone->bi_bdev = pc->dev->bdev;
}

static void passthrud_io(struct work_struct *work)
{
        struct passthru_io *io = container_of(work, struct passthru_io, work);
        struct passthru_c *pc = io->pc;
        struct bio *base_bio = io->base_bio;
        struct bio *clone;

        clone = bio_clone_bioset(base_bio, GFP_NOIO, pc->bs);
        if (!clone) {
                io->error = -ENOMEM;
                passthru_io_release(io);
                return;
        }

        clone_init(io, clone);
        generic_make_request(clone);
}

static void passthru_queue_io(struct passthru_io *io)
{
        struct passthru_c *pc = io->pc;

        INIT_WORK(&io->work, passthrud_io);
        queue_work(pc->io_queue, &io->work);
}

static int passthru_map(struct dm_target *ti, struct bio *bio)
{
        struct passthru_io *io;
        struct passthru_c *pc = ti->private;

        io = passthru_io_alloc(pc, bio);
        passthru_queue_io(io);
        return DM_MAPIO_SUBMITTED;
}

static void passthru_status(struct dm_target *ti, status_type_t type,
                            unsigned status_flags, char *result, unsigned maxlen)
{
        struct passthru_c *pc = (struct passthru_c *) ti->private;

        switch (type) {
        case STATUSTYPE_INFO:
                result[0] = '\0';
                break;

        case STATUSTYPE_TABLE:
                snprintf(result, maxlen, "%s", pc->dev->name);
                break;
        }
}

static struct target_type passthru_target = {
        .name   = "passthru",
        .version = {1, 2, 1},
        .module = THIS_MODULE,
        .ctr    = passthru_ctr,
        .dtr    = passthru_dtr,
        .map    = passthru_map,
        .status = passthru_status,
};

int __init dm_passthru_init(void)
{
        int r;
  
        _passthru_io_pool = KMEM_CACHE(passthru_io, 0);
        if (!_passthru_io_pool)
                return -ENOMEM;
  
        r = dm_register_target(&passthru_target);

        if (r < 0) {
                DMERR("register failed %d", r);
                kmem_cache_destroy(_passthru_io_pool);
        }

        return r;
}

void dm_passthru_exit(void)
{
        dm_unregister_target(&passthru_target);
}

module_init(dm_passthru_init)
module_exit(dm_passthru_exit)

MODULE_DESCRIPTION(DM_NAME " passthrough target with workqueues.");
MODULE_LICENSE("GPL");
