#!/usr/bin/env python

import datetime
import glob
import optparse
import os
import re
import sys
import time

usage = "usage: %prog [options] [directory1] [directory2]"
parser = optparse.OptionParser(usage)
parser.add_option("--max-age", action="store",
                  type = "int", dest = "max_age_days",
                  default = 3, help = "number of runs")
options, args = parser.parse_args()

now = int(time.time())

expire_before = now - options.max_age_days*24*60*60

print 'expiring files before %s' % datetime.datetime.fromtimestamp(expire_before)

if not args:
    # default assume run from root of eideticker directory
    dirs = [ 'src/dashboard/videos/', 'captures/' ]
else:
    dirs = args

files = []
for dir in dirs:
    for ext in [ 'webm', 'zip', 'cache' ]:
        files.extend(glob.glob('%s/*.%s' % (dir, ext)))

stamped_file_re = re.compile('-(\d{10})(\.?)(\d+)?.[^\.]+$')

to_expire = []

for f in files:
    m = re.search(stamped_file_re, f)
    if not m:
        continue
    timestamp = int(m.group(1))
    if timestamp < expire_before:
        to_expire.append(f)

print 'expiring %d files' % len(to_expire)
for f in to_expire:
    os.unlink(f)

