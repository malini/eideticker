#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import json
import mozhttpd
import mozprofile
import optparse
import os
import subprocess
import sys
import time
import urllib
import urlparse
import videocapture
import StringIO
import eideticker

BINDIR = os.path.dirname(__file__)
CAPTURE_DIR = os.path.abspath(os.path.join(BINDIR, "../captures"))
TEST_DIR = os.path.abspath(os.path.join(BINDIR, "../src/tests"))
EIDETICKER_TEMP_DIR = "/tmp/eideticker"

capture_controller = videocapture.CaptureController(custom_tempdir=EIDETICKER_TEMP_DIR)

class CaptureServer(object):
    finished = False
    controller_finishing = False
    start_frame = None
    end_frame = None

    def __init__(self, capture_metadata, capture_file,
                 checkerboard_log_file, capture_controller, device, actions, gestures=None):
        self.capture_metadata = capture_metadata
        self.capture_file = capture_file
        self.checkerboard_log_file = checkerboard_log_file
        self.capture_controller = capture_controller
        self.device = device
        self.actions = actions
        self.gestures = gestures or None

    def terminate_capture(self):
        if self.capture_file and self.capture_controller.capturing:
            self.capture_controller.terminate_capture()

    @mozhttpd.handlers.json_response
    def start_capture(self, request):
        if self.capture_file:
            print "Starting capture on device '%s' with mode: '%s'" % (self.capture_metadata['device'],
                                                                       self.device.hdmiResolution)
            self.capture_controller.start_capture(self.capture_file,
                                                  self.device.hdmiResolution,
                                                  self.capture_metadata)

        return (200, {'capturing': True})

    @mozhttpd.handlers.json_response
    def end_capture(self, request):
        self.finished = True
        self.terminate_capture()
        return (200, {'capturing': False})

    @mozhttpd.handlers.json_response
    def input(self, request):
        if self.gestures:
            if self.checkerboard_log_file:
                self.device.clear_logcat()
            if self.capture_file:
                self.start_frame = self.capture_controller.capture_framenum()
            output = StringIO.StringIO()
            self.device.shell(["sh", self.gestures], output)
        elif self.actions: # startup test currently indicated by no actions
            commandset = urlparse.parse_qs(request.body)['commands'][0]

            if not self.actions.get(commandset) or not \
                    self.actions[commandset].get(self.device.model):
                print "Could not get actions for commandset '%s', model " \
                    "'%s'" % (commandset, self.device.model)
                sys.exit(1)

            def executeCallback():
                if self.checkerboard_log_file:
                    self.device.clear_logcat()
                if self.capture_file:
                    self.start_frame = self.capture_controller.capture_framenum()
                print "Executing commands '%s' for device '%s' (time: %s, framenum: %s)" % (
                    commandset, self.device.model, time.time(), self.start_frame)

            self.device.executeCommands(self.actions[commandset][self.device.model],
                                        executeCallback=executeCallback)

        if self.capture_file:
            self.end_frame = self.capture_controller.capture_framenum()

        print "Finished (time: %s, framenum: %s)" % (time.time(),
                                                     self.end_frame)

        if self.checkerboard_log_file:
            # sleep a bit to make sure we get all the checkerboard stats from
            # test
            time.sleep(1)
            with open(self.checkerboard_log_file, 'w') as f:
                output = self.device.get_logcat(["GeckoLayerRendererProf:D",
                                                 "*:S"])
                f.write(output)

        return (200, {})

def main(args=sys.argv[1:]):
    usage = "usage: %prog [options] <appname> <test path>"
    parser = eideticker.OptionParser(usage=usage)
    parser.add_option("--url-params", action="store",
                      dest="url_params",
                      help="additional url parameters for test")
    parser.add_option("--name", action="store",
                      type = "string", dest = "capture_name",
                      help = "name to give capture")
    parser.add_option("--capture-file", action="store",
                      type = "string", dest = "capture_file",
                      help = "name to give to capture file")
    parser.add_option("--no-capture", action="store_true",
                      dest = "no_capture",
                      help = "run through the test, but don't actually "
                      "capture anything")
    parser.add_option("--checkerboard-log-file", action="store",
                      type = "string", dest = "checkerboard_log_file",
                      help = "name to give checkerboarding stats file")
    parser.add_option("--startup-test", action="store_true",
                      dest="startup_test",
                      help="do a startup test: full capture, no actions")
    parser.add_option("--b2g", action="store_true",
                      dest="b2g", default=False,
                      help="Run in B2G environment. You do not need to pass an appname")
    parser.add_option("--gesture-file", action="store",
                      dest="gesture_file", default=None,
                      help="Path to gesture file on the phone. Will execute this file after test URL loads.")
    parser.add_option("--profile-file", action="store",
                      type="string", dest = "profile_file",
                      help="Collect a performance profile using the built in profiler.")

    options, args = parser.parse_args()
    testpath, appname = None, None
    if options.b2g:
        if len(args) != 1:
            parser.error("incorrect number of arguments")
            sys.exit(1)
        testpath = args[0]
    else:
        if len(args) != 2:
            parser.error("incorrect number of arguments")
            sys.exit(1)

        (appname, testpath) = args
    # Tests must be in src/tests/... unless it is a startup test and the
    # path is about:home (indicating we want to measure startup to the
    # home screen)
    if options.startup_test and testpath == "about:home":
        testpath_rel = testpath
        capture_timeout = 5 # 5 seconds to wait for fennec to start after it claims to have started
    else:
        capture_timeout = None
        try:
            testpath_rel = os.path.abspath(testpath).split(TEST_DIR)[1][1:]
        except:
            print "Test must be relative to %s" % TEST_DIR
            sys.exit(1)

    actions = None
    if not options.startup_test:
        actions_path = os.path.join(os.path.dirname(testpath), "actions.json")
        try:
            with open(actions_path) as f:
                actions = json.loads(f.read())
        except EnvironmentError:
            print "Couldn't open actions file '%s'" % actions_path
            sys.exit(1)

    if not os.path.exists(EIDETICKER_TEMP_DIR):
        os.mkdir(EIDETICKER_TEMP_DIR)
    if not os.path.isdir(EIDETICKER_TEMP_DIR):
        print "Could not open eideticker temporary directory"
        sys.exit(1)

    capture_name = options.capture_name
    if not capture_name:
        capture_name = testpath_rel
    capture_file = options.capture_file
    if not capture_file and not options.no_capture:
        capture_file = os.path.join(CAPTURE_DIR, "capture-%s.zip" %
                                         datetime.datetime.now().isoformat())

    # Create a device object to interface with the phone
    device = eideticker.getDevice(options)

    if appname and device.processExist(appname):
        print "An instance of %s is running. Please stop it before running Eideticker." % appname
        sys.exit(1)

    # If we're logging checkerboard stats, set that up here (seems like it
    # takes a second or so to accept the new setting, so let's do that here --
    # ideally we would detect when that's working, but I'm not sure how to do
    # so trivially)
    if options.checkerboard_log_file:
        old_log_val = device.getprop("log.tag.GeckoLayerRendererProf")
        device.setprop("log.tag.GeckoLayerRendererProf", "DEBUG")

    print "Creating webserver..."
    capture_metadata = {
        'name': capture_name,
        'testpath': testpath_rel,
        'app': appname,
        'device': device.model,
        'startupTest': options.startup_test
        }
    capture_server = CaptureServer(capture_metadata,
                                   capture_file,
                                   options.checkerboard_log_file,
                                   capture_controller, device, actions, options.gesture_file)
    host = mozhttpd.iface.get_lan_ip()
    http = mozhttpd.MozHttpd(docroot=TEST_DIR,
                             host=host, port=0,
                             urlhandlers = [ { 'method': 'GET',
                                               'path': '/api/captures/start/?',
                                               'function': capture_server.start_capture },
                                             { 'method': 'GET',
                                               'path': '/api/captures/end/?',
                                               'function': capture_server.end_capture },
                                             { 'method': 'POST',
                                               'path': '/api/captures/input/?',
                                               'function': capture_server.input } ])
    http.start(block=False)

    connected = False
    tries = 0
    while not connected and tries < 20:
        tries+=1
        import socket
        s = socket.socket()
        try:
            s.connect((host, http.httpd.server_port))
            connected = True
        except Exception:
            print "Can't connect to %s:%s, retrying..." % (host, http.httpd.server_port)

    if not connected:
        print "Could not open webserver. Error!"
        sys.exit(1)

    # note: url params for startup tests currently not supported
    if options.url_params:
        testpath_rel += "?%s" % urllib.quote_plus(options.url_params)

    if options.startup_test:
        if testpath == "about:home":
            url = testpath
        else:
            url = "http://%s:%s/%s?startup_test=1" % (host, http.httpd.server_port, testpath_rel)
    else:
        url = "http://%s:%s/start.html?testpath=%s" % (host,
                                                       http.httpd.server_port,
                                                       testpath_rel)
    print "Test URL is: %s" % url
    if options.b2g:
        runner = eideticker.B2GRunner(device, url, EIDETICKER_TEMP_DIR)
    else: 
        runner = eideticker.BrowserRunner(device, appname, url)
    # FIXME: currently start capture before launching app because we wait until app is
    # launched -- would be better to make waiting optional and then start capture
    # after triggering app launch to reduce latency?
    if options.startup_test and not options.no_capture:
        capture_controller.start_capture(capture_file, device.hdmiResolution,
                                         capture_metadata)
    runner.start(profile_file=options.profile_file)

    # Keep on capturing until we timeout
    if capture_timeout:
        timeout = capture_timeout
    else:
        timeout = 100
    timer = 0
    interval = 0.1

    try:
        while not capture_server.finished and timer < timeout:
            time.sleep(interval)
            timer += interval
    except KeyboardInterrupt:
        print "Aborting"
        runner.stop()
        capture_server.terminate_capture()
        sys.exit(1)

    if capture_timeout and not capture_server.finished:
        capture_server.terminate_capture()
    elif not capture_server.finished:
        print "Did not finish test! Error!"
        runner.stop()
        capture_server.terminate_capture()
        sys.exit(1)

    runner.stop()
    if capture_file:
        print "Converting capture..."
        try:
            capture_controller.convert_capture(capture_server.start_frame, capture_server.end_frame)
        except KeyboardInterrupt:
            print "Aborting"
            sys.exit(1)

    # Clean up checkerboard logging preferences
    if options.checkerboard_log_file:
        device.setprop("log.tag.GeckoLayerRendererProf", old_log_val)


main()
