# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import mozprofile
import os
import time
import socket
import StringIO
import subprocess
import sys

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

    def start(self):
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

            args.extend(["-profile", self.remote_profile_dir])

            # sometimes fennec fails to start, so we'll try three times...
            for i in range(3):
                print "Launching fennec (try %s of 3)" % (i+1)
                if self.dm.launchFennec(self.appname, url=self.url, extraArgs=args):
                    return
            raise Exception("Failed to start Fennec after three tries")
        else:
            self.dm.launchApplication(self.appname, self.activity, self.intent,
                                      url=self.url)

    def stop(self):
        self.dm.killProcess(self.appname)
        if not self.dm.removeDir(self.remote_profile_dir):
            print "WARNING: Failed to remove profile (%s) from device" % self.remote_profile_dir
