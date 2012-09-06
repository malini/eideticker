#!/usr/bin/env python

import eideticker
import json
import mozdevice
import optparse
import os
import subprocess
import sys
import time
import videocapture
import uuid
import zipfile
from eideticker.products import default_products

class NestedDict(dict):
    def __getitem__(self, key):
        if key in self:
            return self.get(key)
        return self.setdefault(key, NestedDict())

default_tests = [
    {
        'name': 'clock',
        'path': 'src/tests/ep1/clock/index.html'
    },
    {
        'name': 'taskjs',
        'path': 'src/tests/ep1/taskjs.org/index.html'
    },
    {
        'name': 'nightly',
        'path': 'src/tests/ep1/nightly.mozilla.org/index.html'
    },
    {
        'name': 'nytimes-scroll',
        'path': 'src/tests/ep1/nytimes/nytimes.com/index.html',
        'urlparams': 'testtype=scroll'
    },
    {
        'name': 'nytimes-zoom',
        'path': 'src/tests/ep1/nytimes/nytimes.com/index.html',
        'urlparams': 'testtype=zoom'
    },
    {
        'name': 'cnn',
        'path': 'src/tests/ep1/cnn/cnn.com/index.html'
    },
    {
        'name': 'reddit',
        'path': 'src/tests/ep1/reddit.com/www.reddit.com/index.html'
    },
    {
        'name': 'imgur',
        'path': 'src/tests/ep1/imgur.com/imgur.com/gallery/index.html'
    },
    {
        'name': 'wikipedia',
        'path': 'src/tests/ep1/en.wikipedia.org/en.wikipedia.org/wiki/Rorschach_test.html'
    }
]

DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "../downloads")
CAPTURE_DIR = os.path.join(os.path.dirname(__file__), "../captures")
GECKO_PROFILER_ADDON_DIR = os.path.join(os.path.dirname(__file__), "../src/GeckoProfilerAddon")

def kill_app(dm, appname):
    procs = dm.getProcessList()
    for (pid, name, user) in procs:
      if name == appname:
        dm.runCmd(["shell", "echo kill %s | su" % pid])

def symbolicate_profile_package(profile_package, profile_path, profile_file):
    retval = subprocess.call(["./symbolicate.sh",
                              os.path.abspath(profile_package), os.path.abspath(profile_file)],
                              cwd=GECKO_PROFILER_ADDON_DIR)
    if retval == 0:
        return profile_path
    else:
        return None

def runtest(dm, product, current_date, appname, appinfo, test, capture_name,
            outputdir, datafile, data, enable_profiling=False):
    capture_file = os.path.join(CAPTURE_DIR,
                                "%s-%s-%s-%s.zip" % (test['name'],
                                                     appname,
                                                     appinfo.get('date'),
                                                     int(time.time())))
    if enable_profiling:
        profile_package = os.path.join(CAPTURE_DIR,
                                       "profile-package-%s-%s-%s-%s.zip" % (test['name'],
                                                                            appname,
                                                                            appinfo.get('date'),
                                                                            int(time.time())))

    urlparams = test.get('urlparams', '')

    test_completed = False
    for i in range(3):
        print "Running test (try %s of 3)" % (i+1)

        args = ["runtest.py", "--url-params", urlparams,
                "--name", capture_name, "--capture-file", capture_file ]
        if enable_profiling:
            args.extend(["--profile-file", profile_package])
        retval = subprocess.call(args + [ appname, test['path'] ])
        if retval == 0:
            test_completed = True
            break
        else:
            print "Test failed, retrying..."

    if not test_completed:
        raise Exception("Failed to run test %s for %s (after 3 tries). "
                        "Aborting." % (test['name'], product['name']))


    capture = videocapture.Capture(capture_file)

    # video file
    video_path = os.path.join('videos', 'video-%s.webm' % time.time())
    video_file = os.path.join(outputdir, video_path)
    open(video_file, 'w').write(capture.get_video().read())

    #  profile file
    if enable_profiling:
        profile_path = os.path.join('profiles', 'sps-profile-%s.zip' % time.time())
        profile_file = os.path.join(outputdir, profile_path)
        symbolicated_profile_path = symbolicate_profile_package(profile_package, profile_path, profile_file)
        os.remove(profile_package)

    # frames-per-second / num unique frames
    num_unique_frames = videocapture.get_num_unique_frames(capture)
    fps = videocapture.get_fps(capture)

    # checkerboarding
    checkerboard = videocapture.get_checkerboarding_area_duration(capture)

    # need to initialize dict for product if not there already
    if not data[test['name']].get(product['name']):
        data[test['name']][product['name']] = {}

    if not data[test['name']][product['name']].get(current_date):
        data[test['name']][product['name']][current_date] = []
    datapoint = { 'fps': fps,
                  'uuid': uuid.uuid1().hex,
                  'checkerboard': checkerboard,
                  'uniqueframes': num_unique_frames,
                  'video': video_path,
                  'appdate': appinfo.get('date'),
                  'buildid': appinfo.get('buildid'),
                  'revision': appinfo.get('revision') }
    if enable_profiling:
        datapoint['profile'] = symbolicated_profile_path

    data[test['name']][product['name']][current_date].append(datapoint)

    # Write the data to disk immediately (so we don't lose it if we fail later)
    with open(datafile, 'w') as f:
        f.write(json.dumps(data))

def main(args=sys.argv[1:]):
    usage = "usage: %prog [options] <test> <output dir>"

    parser = eideticker.OptionParser(usage=usage)
    parser.add_option("--enable-profiling",
                      action="store_true", dest = "enable_profiling",
                      help = "Create SPS profile to go along with capture")
    parser.add_option("--device-id", action="store", dest="device_id",
                      help="id of device (used in output json)")
    parser.add_option("--product",
                      action="store", dest="product",
                      help = "Restrict testing to product (options: %s)" %
                      ", ".join([product["name"] for product in default_products]))
    parser.add_option("--num-runs", action="store",
                      type = "int", dest = "num_runs",
                      help = "number of runs (default: 1)")

    options, args = parser.parse_args()
    if len(args) != 2:
        parser.error("incorrect number of arguments")

    (testname, outputdir) = args
    num_runs = 1
    if options.num_runs:
        num_runs = options.num_runs

    testnames = [test["name"] for test in default_tests]
    if testname not in testnames:
        print "ERROR: No tests matching '%s' (options: %s)" % (testname, ", ".join(testnames))
        sys.exit(1)
    else:
        test = [test for test in default_tests if test['name'] == testname][0]

    device_id = options.device_id
    if not device_id:
        device_id = os.environ.get('DEVICE_ID')
    if not device_id:
        print "ERROR: Must specify device id (either with --device-id or with DEVICE_ID environment variable)"
        sys.exit(1)

    products = default_products
    if options.product:
        products = [product for product in default_products if product['name'] == options.product]
        if not products:
            print "ERROR: No products matching '%s'" % options.product
            sys.exit(1)

    current_date = time.strftime("%Y-%m-%d")
    datafile = os.path.join(outputdir, 'data-%s.json' % device_id)

    data = NestedDict()
    if os.path.isfile(datafile):
        data.update(json.loads(open(datafile).read()))

    device = eideticker.getDevice(options)

    # update the device list for the dashboard
    devices = {}
    devicefile = os.path.join(outputdir, 'devices.json')
    if os.path.isfile(devicefile):
        devices = json.loads(open(devicefile).read())['devices']
    devices[device_id] = { 'name': device.model,
                           'version': device.getprop('ro.build.version.release') }
    with open(devicefile, 'w') as f:
        f.write(json.dumps({ 'devices': devices }))

    for product in products:
        if product.get('url'):
            product_fname = os.path.join(DOWNLOAD_DIR, "%s.apk" % product['name'])
            appinfo = eideticker.get_fennec_appinfo(product_fname)
            appname = appinfo['appname']
            capture_name = "%s %s" % (product['name'], appinfo['date'])
        else:
            appinfo = { }
            appname = product['appname']
            capture_name = "%s (taken on %s)" % (product['name'], current_date)

        if appinfo.get('appname'):
            appname = appinfo['appname']
        else:
            appname = product['appname']

        # Run the test the specified number of times
        for i in range(num_runs):
            # Kill any existing instances of the processes
            device.killProcess(appname)

            # Now run the test
            runtest(device, product, current_date, appname, appinfo, test,
                    capture_name + " #%s" % i, outputdir, datafile, data,
                    enable_profiling=options.enable_profiling)

            # Kill app after test complete
            device.killProcess(appname)

main()
