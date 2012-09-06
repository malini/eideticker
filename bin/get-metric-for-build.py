#!/usr/bin/env python

import datetime
import eideticker
import json
import mozdevice
from mozregression.runnightly import FennecNightly
from mozregression.utils import get_date
import optparse
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib2
import videocapture
import zipfile

CAPTURE_DIR = os.path.join(os.path.dirname(__file__), "../captures")
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "../downloads")
CHECKERBOARD_REGEX = re.compile('.*GeckoLayerRendererProf.*1000ms:.*\ '
                                '([0-9]+\.[0-9]+)\/([0-9]+).*')

def parse_checkerboard_log(fname):
    checkerboarding_percent_totals = 0.0
    with open(fname) as f:
        for line in f.readlines():
            match = CHECKERBOARD_REGEX.search(line.rstrip())
            if match:
                (amount, total) = (float(match.group(1)), float(match.group(2)))
                checkerboarding_percent_totals += (total - amount)

    return checkerboarding_percent_totals

def get_build_for_date(date):
    fname = os.path.join(DOWNLOAD_DIR,
                         "nightly-%s-%s-%s.apk" % (date.year,
                                                   date.month,
                                                   date.day))
    if os.path.exists(fname):
        print "Build already exists for %s. Skipping download." % date
        return fname

    fennec = FennecNightly()
    build_url = fennec.getBuildUrl(date)
    if not build_url:
        print "ERROR: Couldn't get build url for date %s" % date
        return None

    print "Downloading %s" % build_url
    dl = urllib2.urlopen(build_url)
    with open(fname, 'w') as f:
        f.write(dl.read())

    return fname

def run_test(device, outputdir, outputfile, test, url_params, num_runs,
             startup_test, no_capture, get_internal_checkerboard_stats, apk=None,
             appname = None, appdate = None, profile_file=None):
    if apk:
        appinfo = eideticker.get_fennec_appinfo(apk)
        appname = appinfo['appname']
        print "Installing %s (version: %s, revision %s)" % (appinfo['appname'],
                                                            appinfo['version'],
                                                            appinfo['revision'])
        device.updateApp(apk)
    else:
        appinfo = None

    captures = []

    for i in range(num_runs):
        # Kill any existing instances of the processes
        device.killProcess(appname)

        # Now run the test
        capture_file = os.path.join(CAPTURE_DIR,
                                    "metric-test-%s-%s.zip" % (appname,
                                                               int(time.time())))
        args = ["runtest.py", "--url-params", url_params, appname, test]
        if get_internal_checkerboard_stats:
            checkerboard_logfile = tempfile.NamedTemporaryFile()
            args.extend(["--checkerboard-log-file", checkerboard_logfile.name])
        if startup_test:
            args.extend(["--startup-test"])
        if no_capture:
            args.extend(["--no-capture"])
        else:
            args.extend(["--capture-file", capture_file])
        if profile_file:
            args.extend(["--profile-file", profile_file])
        print args
        retval = subprocess.call(args)
        if retval != 0:
            raise Exception("Failed to run test %s for %s" % (test, appname))

        capture_result = {}
        if not no_capture:
            capture_result['file'] = capture_file

            capture = videocapture.Capture(capture_file)

            framediff_sums = videocapture.get_framediff_sums(capture)
            if startup_test:
                capture_result['stableframe'] = videocapture.get_stable_frame(capture)
            else:
                capture_result['uniqueframes'] = videocapture.get_num_unique_frames(capture)
                capture_result['fps'] = videocapture.get_fps(capture)
                capture_result['checkerboard'] = videocapture.get_checkerboarding_area_duration(capture)
            if outputdir:
                video_path = os.path.join('videos', 'video-%s.webm' % time.time())
                video_file = os.path.join(outputdir, video_path)
                open(video_file, 'w').write(capture.get_video().read())
                capture_result['video'] = video_path

        if get_internal_checkerboard_stats:
            internal_checkerboard_totals = parse_checkerboard_log(checkerboard_logfile.name)
            capture_result['internalcheckerboard'] = internal_checkerboard_totals

        captures.append(capture_result)

    appkey = appname
    if appdate:
        appkey = appdate.isoformat()
    else:
        appkey = appname

    if appinfo and appinfo.get('revision'):
        display_key = "%s (%s)" % (appkey, appinfo['revision'])
    else:
        display_key = appkey
    print "=== Results for %s ===" % display_key

    if not no_capture:
        if startup_test:
            print "  First stable frames:"
            print "  %s" % map(lambda c: c['stableframe'], captures)
            print
        else:
            print "  Number of unique frames:"
            print "  %s" % map(lambda c: c['uniqueframes'], captures)
            print

            print "  Average number of unique frames per second:"
            print "  %s" % map(lambda c: c['fps'], captures)
            print

            print "  Checkerboard area/duration (sum of percents NOT percentage):"
            print "  %s" % map(lambda c: c['checkerboard'], captures)
            print

        print "  Capture files (for further reference):"
        print "  Capture files: %s" % map(lambda c: c['file'], captures)
        print

    if get_internal_checkerboard_stats:
        print "  Internal Checkerboard Stats (sum of percents, not percentage):"
        print "  %s" % map(lambda c: c['internalcheckerboard'], captures)
        print

    if outputfile:
        resultdict = { 'title': test, 'data': {} }
        if os.path.isfile(outputfile):
            resultdict.update(json.loads(open(outputfile).read()))

        if not resultdict['data'].get(appkey):
            resultdict['data'][appkey] = []
        resultdict['data'][appkey].extend(captures)

        with open(outputfile, 'w') as f:
            f.write(json.dumps(resultdict))

def main(args=sys.argv[1:]):
    usage = "usage: %prog <test> [appname1] [appname2] ..."
    parser = eideticker.OptionParser(usage=usage)
    parser.add_option("--num-runs", action="store",
                      type = "int", dest = "num_runs",
                      default=1,
                      help = "number of runs (default: 1)")
    parser.add_option("--output-dir", action="store",
                      type="string", dest="outputdir",
                      help="output results to json file")
    parser.add_option("--no-capture", action="store_true",
                      dest = "no_capture",
                      help = "run through the test, but don't actually "
                      "capture anything")
    parser.add_option("--profile-file", action="store",
                      type="string", dest = "profile_file",
                      help="Collect a performance profile using the built in profiler.")
    parser.add_option("--get-internal-checkerboard-stats",
                      action="store_true",
                      dest="get_internal_checkerboard_stats",
                      help="get and calculate internal checkerboard stats")
    parser.add_option("--startup-test",
                      action="store_true",
                      dest="startup_test",
                      help="measure startup times instead of normal metrics")
    parser.add_option("--url-params", action="store",
                      dest="url_params", default="",
                      help="additional url parameters for test")
    parser.add_option("--use-apks", action="store_true", dest="use_apks",
                      help="use and install android APKs as part of test (instead of specifying appnames)")
    parser.add_option("--date", action="store", dest="date",
                      metavar="YYYY-MM-DD",
                      help="get and test nightly build for date")
    parser.add_option("--start-date", action="store", dest="start_date",
                      metavar="YYYY-MM-DD",
                      help="start date for range of nightlies to test")
    parser.add_option("--end-date", action="store", dest="end_date",
                      metavar="YYYY-MM-DD",
                      help="end date for range of nightlies to test")

    options, args = parser.parse_args()

    if len(args) == 0:
        parser.error("Must specify at least one argument: the path to the test")

    dates = []
    appnames = []
    apks = []
    if options.start_date and options.end_date and len(args) == 1:
        test = args[0]
        start_date = get_date(options.start_date)
        end_date = get_date(options.end_date)
        days=(end_date-start_date).days
        for numdays in range(days+1):
            dates.append(start_date+datetime.timedelta(days=numdays))
    elif options.date and len(args) == 1:
        test = args[0]
        dates = [get_date(options.date)]
    elif not options.date and len(args) >= 2:
        test = args[0]
        if options.use_apks:
            apks = args[1:]
        else:
            appnames = args[1:]
    elif not options.date or (not options.start_date and not options.end_date):
        parser.error("Must specify date, date range, a set of appnames (e.g. org.mozilla.fennec) or a set of apks (if --use-apks is specified)")

    device = eideticker.getDevice(options)

    if options.outputdir:
        outputfile = os.path.join(options.outputdir, "metric-test-%s.json" % time.time())
    else:
        outputfile = None

    if appnames:
        for appname in appnames:
            run_test(device, options.outputdir, outputfile, test,
                     options.url_params,
                     options.num_runs,
                     options.startup_test,
                     options.no_capture,
                     options.get_internal_checkerboard_stats, appname=appname,
                     profile_file=options.profile_file)
    elif apks:
        for apk in apks:
            run_test(device, options.outputdir,
                     outputfile, test,
                     options.url_params,
                     options.num_runs,
                     options.startup_test,
                     options.no_capture,
                     options.get_internal_checkerboard_stats, apk=apk,
                     profile_file=options.profile_file)
    else:
        for date in dates:
            apk = get_build_for_date(date)
            run_test(device, options.outputdir,
                     outputfile, test,
                     options.url_params,
                     options.num_runs,
                     options.startup_test,
                     options.no_capture,
                     options.get_internal_checkerboard_stats, apk=apk,
                     appdate=date,
                     profile_file=options.profile_file)


main()
