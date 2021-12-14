#!/usr/bin/python

import argparse

parser = argparse.ArgumentParser(description="Generate device mapper target installation command.")

parser.add_argument("device", help="Disk device the target will wrap.")
parser.add_argument("size", help="Size of the disk device", type=int)
parser.add_argument("track_size", help="Size of track in bytes", type=int)
parser.add_argument("band_size_tracks", help="Band size in tracks", type=int)
parser.add_argument("cache_percent", help="Cache region percentage", type=int)

args = parser.parse_args()

PBA_SIZE = 4096
LBA_SIZE = 512

band_size = args.band_size_tracks * args.track_size
band_size_pbas = band_size / PBA_SIZE
nr_bands = args.size / band_size
nr_cache_bands = nr_bands * args.cache_percent / 100
cache_size = nr_cache_bands * band_size
nr_usable_bands = (nr_bands / nr_cache_bands - 1) * nr_cache_bands
usable_size = nr_usable_bands * band_size
usable_lbas = usable_size / LBA_SIZE

print "0 %d sadc %s %d %d %d %d" % \
    (usable_lbas, args.device, args.track_size, args.band_size_tracks, \
     args.cache_percent, args.size)
