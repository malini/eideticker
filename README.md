Project Eideticker
==================

Project Eideticker is an automated test harness that captures and analyzes
browser output via HDMI. It currently only supports various browsers (Fennec,
Stock) on Android, but support for other platforms is planned. There is
experimental support for B2G on the pandaboard.

### Requirements

* Linux system with zip, ffmpeg, g++, python 2.7 development and virtualenv
  installed. On Ubuntu, you can get this setup by running:

    `sudo apt-get install -y zip ffmpeg g++ python2.7-dev python-virtualenv`

* Blackmagic Design DeckLink HD Extreme 3D card and the appropriate drivers if
  you want to actually capture video (it is possible to use the Eideticker
  harness without the video capture step, which can be useful for certain
  cases: see below).

* Installed Android SDK with the tools in your path. Please follow the
  instructions at https://wiki.mozilla.org/Mobile/Fennec/Android#Setup_a_Build_Environment

* A supported mobile phone running Android with Orangutan installed in
  `/system/ Eideticker's tests are specifically tuned for specific screen
  dimensions. Currently only the LG G2X (running in portrait mode) and the
  Galaxy Nexus (running in landscape) are supported. Your device must also be
  rooted and, if using SUTAgent, you must configure the su binary to
  automatically allow SUTAgent to run commands as root in silent mode (so that
  notifications don't pop up while running tests). For information on installing
  Orangutan, see that project's README at http://github.com/wlach/orangutan.

### Installation

Run `bootstrap.sh` in the root directory to set everything up.

### Usage

Eideticker is meant to be run in a virtualenv, so the first step is to set
that up in your shell by running this command within the root directory:

    source ./bin/activate

The next step depends on whether you're using ADB or SUTAgent to interface
with the device. If the former, just connect your Android device to your
computer's USB port. That's it, you should now be set to run tests!

If you're using SUTAgent, you'll want to start the SUTAgent app, note the
ip address of your phone, then set the following environment variables:

    export DM_TRANS=sut
    export TEST_DEVICE=<device ip of phone>

If you are using a B2G pandaboard with adb, then you'll need sudo privileges for adb:

    adb kill-server
    sudo adb start-server

#### Console Mode

Console mode is meant for internal profiling. You run a program
called get-metric-for-build.py with a specific test against an Android apk,
and out will pop several results. This is not yet supported for B2G.

    ./bin/get-metric-for-build.py --use-apks <test> <apk of build 1> [apk of build 2] ...

For example, to run the canvas clock example against Fennec nightly, try
this:

    ./bin/get-metric-for-build.py --use-apks src/tests/ep1/clock.html nightly.apk

Typically, you want to run Eideticker more than once on a particular test to
get a range of results as tests are not 100% deterministic (partly due to the
way we run tests, partly due to Android itself). You can do this with the
`--num-runs` option. For example:

    ./bin/get-metric-for-build.py --use-apks --num-runs 5 src/tests/ep1/clock.html nightly.apk

If you want to know more about the results (where the numbers are coming from)
you can open them up inside the Eideticker web interface. To open it, execute:

    ./bin/webapp.sh

Then connect to http://localhost:8080. You should see a list of captures, select
the one you're interested in to dive into fine grained detail.

In addition to supporting HDMI capture and analysis, it is also possible to run
the Eideticker harness in a mode that simply "captures" the performance log
of Fennec and outputs results. This has two advantages: first, you don't need
any kind of specialized hardware. Second, it's much faster (since there's no
video encoding/decoding/analysis step). For this you want to pass in
"--no-capture" and "--get-internal-checkerboard-stats", like so:

    ./bin/get-metric-for-build.py --use-apks --no-capture --get-internal-checkerboard-stats src/tests/ep1/taskjs.org/index.html nightly.apk

#### Dashboard Mode

Dashboard mode is used to generate a dashboard of eideticker results, like
what you see at http://wrla.ch/eideticker/dashboard. From a toplevel, it
is run from a script called `bin/run-update-dashboard.sh`, which can be called
standalone. This script then it turn calls another script called
`bin/update-dashboard.py` with various arguments corresponding to firefox
version, test to run, etc. The dashboard is currently under heavy development
and is not meant to be a developer/qa facing tool. For now, if you have need
to use/modify it, please refer to the source. This is not yet supported for B2G.

### Eideticker "tests"

Eideticker tests are simply static HTML with a bit of JavaScript glue to
interface with the harness and some JSON metadata to describe actions that
Eideticker should perform while a capture is ongoing. The simplest example
of a test would probably be the clock demo, which you can find in
`src/tests/ep1/clock/index.html` (you have to run `./bootstrap.sh first to
checkout the ep1 submodule before you can find this file).

Writing your own tests is a matter of adding a subdirectory to `src/tests`,
creating/copying an HTML page of your choice, adding the relevant JavaScript
code to start/stop the test as appropriate, and then making an actions.json
file with whatever actions you want to simulate during the test.
