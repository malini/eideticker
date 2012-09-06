# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import mozprofile
import os
import tempfile
import time
import socket
import StringIO
import subprocess
import sys
import zipfile

from marionette import Marionette
from mozdevice import B2GManager

class B2GRunner(object):
    remote_profile_dir = None

    def __init__(self, dm, url, tmpdir, mode=None, marionette_host=None, marionette_port=None):
        self.dm = dm
        self.url = url
        self.mode = mode or 'portrait'
        self.bm = B2GManager(dm, tmpdir, marionette_host=marionette_host, marionette_port=marionette_port)

    def start(self):
        prefs = """
user_pref("power.screen.timeout", 999999);  
        """
        print "forward port"
        self.bm.forward_port()
        print "setting up profile"
        self.bm.setup_profile(prefs)
        print "setting up ethernet"
        self.bm.setup_ethernet()
        print "done"

        #launch app
        session = self.bm.marionette.start_session()
        if 'b2g' not in session:
            raise Exception("bad session value %s returned by start_session" % session)

        print "launching test"
        #set landscape or portrait mode
        self.bm.marionette.execute_script("screen.mozLockOrientation('%s');" % self.mode)
        # start the tests by navigating to the mochitest url
        self.bm.marionette.execute_script("window.location.href='%s';" % self.url)

    def stop(self):
        self.bm.marionette.delete_session()

class BrowserRunner(object):

    remote_profile_dir = None
    intent = "android.intent.action.VIEW"

    def __init__(self, dm, appname, url):
        self.dm = dm
        self.appname = appname
        self.url = url

        activity_mappings = {
            'com.android.browser': '.BrowserActivity',
            'com.google.android.browser': 'com.android.browser.BrowserActivity',
            'com.android.chrome': '.Main',
            'com.opera.browser': 'com.opera.Opera',
            'mobi.mgeek.TunnyBrowser': '.BrowserActivity' # Dolphin
            }

        # use activity mapping if not mozilla
        if self.appname.startswith('org.mozilla'):
            self.activity = '.App'
            self.intent = None
        else:
            self.activity = activity_mappings[self.appname]

    def get_profile(self, target_file):
        if self.is_profiling == False:
           raise Exception("Can't get profile if it isn't started with the profiling option")

        files_to_package = []

        # create a temporary directory to place the profile and shared libraries
        tmpdir = tempfile.mkdtemp()

        # remove previous profiles if there is one
        profile_path = os.path.join(tmpdir, "fennec_profile.txt")
        if os.path.exists(profile_path):
            os.remove(profile_path)

        print "Fetching fennec_profile.txt"
        self.dm.getFile(self.profile_location, profile_path)
        files_to_package.append(profile_path);

        with zipfile.ZipFile(target_file, "w") as zip_file:
            for file_to_package in files_to_package:
                print "File to zip: " + file_to_package
                zip_file.write(file_to_package, os.path.basename(file_to_package))

    def get_profile_and_symbols(self, target_zip):
        if self.is_profiling == False:
           raise Exception("Can't get profile if it isn't started with the profiling option")

        files_to_package = []

        # create a temporary directory to place the profile and shared libraries
        tmpdir = tempfile.mkdtemp()

        # remove previous profiles if there is one
        profile_path = os.path.join(tmpdir, "fennec_profile.txt")
        if os.path.exists(profile_path):
            os.remove(profile_path)

        print "Fetching fennec_profile.txt"
        self.dm.getFile(self.profile_location, profile_path)
        files_to_package.append(profile_path)

        print "Fetching app symbols"
        try:
            local_apk_path = os.path.join(tmpdir, "symbol.apk")
            self.dm.getAPK(self.appname, local_apk_path)
            files_to_package.append(local_apk_path)
        except:
            print "WARNING: Failed to fetch app symbols"
            pass # We still get a useful profile without the symbols from the apk

        # get all the symbols library for symbolication
        print "Fetching system libraries"
        libpaths = [ "/system/lib",
                     "/system/lib/egl",
                     "/system/lib/hw",
                     "/system/vendor/lib",
                     "/system/vendor/lib/egl",
                     "/system/vendor/lib/hw",
                     "/system/b2g" ]

        for libpath in libpaths:
             print "Fetching from: " + libpath
             dirlist = self.dm.listFiles(libpath)
             for filename in dirlist:
                 filename = filename.strip()
                 if filename.endswith(".so"):
                     try:
                         lib_path = os.path.join(tmpdir, filename)
                         results = self.dm.getFile(libpath + '/' + filename, lib_path)
                         if results != None:
                             files_to_package.append(lib_path);
                     except subprocess.CalledProcessError:
                         print "failed to fetch: " + fileName

        with zipfile.ZipFile(target_zip, "w") as zip_file:
            for file_to_package in files_to_package:
                zip_file.write(file_to_package, os.path.basename(file_to_package))

    def start(self, profile_file=None):
        print "Starting %s... " % self.appname

        # for fennec only, we create and use a profile
        if self.appname.startswith('org.mozilla'):
            args = []
            profile = None
            profile = mozprofile.Profile(preferences = { 'gfx.show_checkerboard_pattern': False,
                                                         'browser.firstrun.show.uidiscovery': False,
                                                         'toolkit.telemetry.prompted': 2 })
            self.remote_profile_dir = "/".join([self.dm.getDeviceRoot(),
                                                os.path.basename(profile.profile)])
            if not self.dm.pushDir(profile.profile, self.remote_profile_dir):
                raise Exception("Failed to copy profile to device")

            self.is_profiling = profile_file != None
            if self.is_profiling:
                self.profile_file = profile_file
                mozEnv = { "MOZ_PROFILER_STARTUP": "true" }
            else:
                mozEnv = None

            args.extend(["-profile", self.remote_profile_dir])

            # sometimes fennec fails to start, so we'll try three times...
            for i in range(3):
                print "Launching fennec (try %s of 3)" % (i+1)
                if self.dm.launchFennec(self.appname, url=self.url, mozEnv=mozEnv, extraArgs=args):
                    return
            raise Exception("Failed to start Fennec after three tries")
        else:
            self.dm.launchApplication(self.appname, self.activity, self.intent,
                                      url=self.url)

    def stop(self):
        # Dump the profile
        if self.is_profiling:
            print "Saving sps performance profile"
            self.dm.sendSaveProfileSignal(self.appname)
            self.profile_location = "/mnt/sdcard/profile_0_%s.txt" % self.dm.getPIDs(self.appname)[0]
            # Saving goes through the main event loop so give it time to flush
            time.sleep(10)

        self.dm.killProcess(self.appname)

        # Process the profile
        if self.is_profiling:
            self.get_profile_and_symbols(self.profile_file)

        if not self.dm.removeDir(self.remote_profile_dir):
            print "WARNING: Failed to remove profile (%s) from device" % self.remote_profile_dir
