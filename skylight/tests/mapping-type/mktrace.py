#!/usr/bin/python

import argparse
import sys

sys.path.append('..')

from lib import gen_trace

parser = argparse.ArgumentParser()
parser.add_argument("device")
parser.add_argument("band_a_offset", type=int)
parser.add_argument("band_b_offset", type=int)
parser.add_argument("track_size", type=int)
parser.add_argument("block_size", type=int)

args = parser.parse_args()

b1 = range(args.band_a_offset, args.band_a_offset + args.track_size,
           args.block_size)
b2 = range(args.band_b_offset, args.band_b_offset + args.track_size,
           args.block_size)

offsets = [v for pair in zip(b1, b2) for v in pair]

args.band_b_offset += args.track_size

b2 = range(args.band_b_offset, args.band_b_offset + args.track_size, args.
           block_size)

offsets += [v for pair in zip(b1, b2) for v in pair]

gen_trace('read', args.device, offsets, args.block_size)
