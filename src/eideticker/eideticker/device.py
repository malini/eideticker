# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import StringIO
import mozdevice
import os
import re
import tempfile
import time

# I know specifying resolution manually like this is ugly, but as far as I
# can tell there is no good, device-independant way of getting this
# information universally (we can get the resolution with SUT, but not the
# required HDMI mode)
DEVICE_PROPERTIES = {
    "Galaxy Nexus": {
        "hdmiResolution": "720p",
        "inputDevice": "/dev/input/event1",
        "dimensions": (1180, 720)
    },
    "Panda": {
        "hdmiResolution": "720p",
        "inputDevice": "/dev/input/event2",
        "dimensions": (1280, 672)
    },
    "LG-P999": {
        "hdmiResolution": "1080p",
        "inputDevice": "/dev/input/event1",
        "dimensions": (480, 800)
    },
    "MID": {
        "hdmiResolution": None,
        "inputDevice": "/dev/input/event2",
        "dimensions": (480, 800)
    },
}

class EidetickerMixin(object):
    """Mixin to extend DeviceManager with functionality to allow it to be
       remotely controlled and other related things"""

    @property
    def hdmiResolution(self):
        return DEVICE_PROPERTIES[self.model]['hdmiResolution']

    @property
    def inputDevice(self):
        return DEVICE_PROPERTIES[self.model]['inputDevice']

    def _init(self):
        self.model = self.getprop("ro.product.model")

        if not DEVICE_PROPERTIES.get(self.model):
            raise Exception("Unsupported device type '%s'" % self.model)

        # Hack: this gets rid of the "finished charging" modal dialog that the
        # LG G2X sometimes brings up
        if self.model == 'LG-P999':
            self.executeCommand("tap", [240, 617])

    # FIXME: make this part of devicemanager
    def _shellCheckOutput(self, args):
        buf = StringIO.StringIO()
        retval = self.shell(args, buf, root=True)
        output = str(buf.getvalue()[0:-1]).rstrip()
        if retval == None:
            raise Exception("Did not successfully run command %s (output: '%s', retval: 'None')" % (args, output))
        if retval != 0:
            raise Exception("Non-zero return code for command: %s (output: '%s', retval: '%i')" % (args, output, retval))
        return output

    def _executeScript(self, events, executeCallback=None):
        '''Executes a set of monkey commands on the device'''
        with tempfile.NamedTemporaryFile() as f:
            f.write("\n".join(events) + "\n")
            f.flush()
            remotefilename = os.path.join(self.getDeviceRoot(),
                                          os.path.basename(f.name))
            self.pushFile(f.name, remotefilename)
            if executeCallback:
                executeCallback()
            self._shellCheckOutput(["/system/xbin/orng", self.inputDevice,
                                    remotefilename])

    def getPIDs(self, appname):
        '''FIXME: Total hack, put this in devicemanagerADB instead'''
        procs = self.getProcessList()
        pids = []
        for (pid, name, user) in procs:
            if name == appname:
                pids.append(pid)
        return pids

    def sendSaveProfileSignal(self, appName):
        pids = self.getPIDs(appName)
        if pids:
            self._shellCheckOutput(['kill', '-s', '12', pids[0]])

    def getAPK(self, appname, localfile):
        remote_tempfile = '/data/local/apk-tmp-%s' % time.time()
        for remote_apk_path in [ '/data/app/%s-1.apk' % appname,
                                 '/data/app/%s-2.apk' % appname ]:
            try:
                self._shellCheckOutput(['dd', 'if=%s' % remote_apk_path,
                                        'of=%s' % remote_tempfile])
                self._shellCheckOutput(['chmod', '0666', remote_tempfile])
                self.removeFile(remote_tempfile)
            except:
                continue

            if self.getFile(remote_tempfile, localfile):
                return

        raise Exception("Unable to get remote APK for %s!" % appname)


    def getprop(self, prop):
        return self._shellCheckOutput(["getprop", str(prop)])

    def setprop(self, prop, value):
        if not value:
            value = ""
        self._shellCheckOutput(["setprop", str(prop), str(value)])

    def clear_logcat(self):
        self._shellCheckOutput(["logcat", "-c"])

    def get_logcat(self, args):
        return self._shellCheckOutput(["logcat", "-d"] + args)

    def _transformXY(self, coords):
        # FIXME: Only handling 90 degrees for now, everything else falls back
        # to default
        if hasattr(self, "rotation") and self.rotation == 90:
            return (self.dimensions[1] - int(coords[1]), int(coords[0]))

        return coords

    def _getDragEvents(self, touch_start, touch_end, duration=1.0, num_steps=5):
        touch_start = self._transformXY(touch_start)
        touch_end = self._transformXY(touch_end)

        return "drag %s %s %s %s %s %s" % (int(touch_start[0]), int(touch_start[1]),
                                           int(touch_end[0]), int(touch_end[1]),
                                           num_steps, int(duration * 1000))

    def _getSleepEvent(self, duration=1.0):
        return "sleep %s" % int(float(duration) * 1000.0)

    def _getTapEvent(self, x, y, times=1):
        coords = self._transformXY((x,y))
        return "tap %s %s %s" % (int(x), int(y), times)

    def _getScrollDownEvents(self, numtimes=1, numsteps=10):
        events = []
        x = int(self.dimensions[0] / 2)
        ybottom = self.dimensions[1] - 200
        ytop = 240
        for i in range(numtimes):
            events.append(self._getDragEvents((x,ybottom), (x,ytop), 0.1,
                                              numsteps))
        return events

    def _getScrollUpEvents(self, numtimes=1, numsteps=10):
        events = []
        x = int(self.dimensions[0] / 2)
        ybottom = self.dimensions[1] - 100
        ytop = 240
        for i in range(numtimes):
            events.append(self._getDragEvents((x,ytop), (x,ybottom), 0.1,
                                              numsteps))
        return events

    def _getCmdEvents(self, cmd, args):
        if cmd == "scroll_down":
            cmdevents = self._getScrollDownEvents(*args)
        elif cmd == "scroll_up":
            cmdevents = self._getScrollUpEvents(*args)
        elif cmd == "tap":
            cmdevents = [self._getTapEvent(*args)]
        elif cmd == "double_tap":
            cmdevents = [self._getTapEvent(*args, times=2)]
        elif cmd == "sleep":
            if len(args):
                cmdevents = [self._getSleepEvent(duration=args[0])]
            else:
                cmdevents = [self._getSleepEvent()]
        else:
            raise Exception("Unknown command")

        return cmdevents

    def executeCommand(self, cmd, args, executeCallback=None):
        cmdevents = self._getCmdEvents(cmd, args)
        if cmdevents:
            self._executeScript(cmdevents, executeCallback=executeCallback)

    def executeCommands(self, cmds, executeCallback=None):
        cmdevents = []
        for cmd in cmds:
            (cmd, args) = (cmd[0], cmd[1:])
            cmdevents.extend(self._getCmdEvents(cmd, args))
        self._executeScript(cmdevents, executeCallback=executeCallback)

class DroidADB(mozdevice.DroidADB, EidetickerMixin):

    def __init__(self, **kwargs):
        mozdevice.DroidADB.__init__(self, **kwargs)
        self._init() # custom eideticker init steps

    def killProcess(self, appname, forceKill=False):
        '''FIXME: Total hack, put this in devicemanagerADB instead'''
        procs = self.getProcessList()
        didKillProcess = False
        for (pid, name, user) in procs:
            if name == appname:
                self.runCmd(["shell", "echo kill %s | su" % pid])
                didKillProcess = True
        return didKillProcess

    @property
    def dimensions(self):
        return DEVICE_PROPERTIES[self.model]['dimensions']

    @property
    def rotation(self):
        return 0 # No way to find real rotation, assume 0

class DroidSUT(mozdevice.DroidSUT, EidetickerMixin):

    cached_dimensions = None
    cached_rotation = None
    def __init__(self, **kwargs):
        mozdevice.DroidSUT.__init__(self, **kwargs)
        self._init() # custom eideticker init steps

    @property
    def dimensions(self):
        if self.cached_dimensions:
            return self.cached_dimensions

        res_string = self.getInfo('screen')['screen'][0]
        m = re.match('X:([0-9]+) Y:([0-9]+)', res_string)
        self.cached_dimensions = (int(m.group(1)), int(m.group(2)))
        return self.cached_dimensions

    @property
    def rotation(self):
        # for now we assume rotation never changes
        if self.cached_rotation:
            return self.cached_rotation

        rot_string = self.getInfo('rotation')['rotation'][0]
        m = re.match('ROTATION:([0-9]+)', rot_string)
        self.cached_rotation = int(m.group(1))
        return self.cached_rotation

    def updateApp(self, appBundlePath, processName=None, destPath=None, ipAddr=None, port=30000):
        '''Replacement for SUT version of updateApp which operates more like the ADB version'''
        '''(FIXME: TOTAL HACK ETC ETC)'''
        basename = os.path.basename(appBundlePath)
        pathOnDevice = os.path.join(self.getDeviceRoot(), basename)
        self.pushFile(appBundlePath, pathOnDevice)
        self.installApp(pathOnDevice)
        self.removeFile(pathOnDevice)

def getDevice(options):
    '''Gets an eideticker device according to parameters'''

    if options.dmtype:
        dmtype = options.dmtype
    else:
        dmtype = os.environ.get('DM_TRANS', 'adb')

    host = options.host
    if not host and dmtype == "sut":
        host = os.environ.get('TEST_DEVICE')
    port = options.port

    print "Using %s interface (host: %s, port: %s)" % (dmtype, host, port)
    if dmtype == "adb":
        if host and not port:
            port = 5555
        return DroidADB(packageName=None, host=host, port=port)
    elif dmtype == "sut":
        if not host:
            raise Exception("Must specify host with SUT!")
        if not port:
            port = 20701
        return DroidSUT(host=host, port=port)
    else:
        raise Exception("Unknown device manager type: %s" % type)
