#!/usr/bin/python

import random
import argparse
import sys

sys.path.append('..')

from lib import gen_trace

parser = argparse.ArgumentParser()
parser.add_argument("device")
parser.add_argument("offset", type=int)
parser.add_argument("estimate", type=int)
parser.add_argument("accuracy", type=int)

args = parser.parse_args()

size = args.estimate * 100

sequential = range(args.offset, args.offset + size, args.accuracy)

scrambled = sequential[:]
random.shuffle(scrambled)

gen_trace('write', args.device, scrambled)
gen_trace('read', args.device, sequential)
