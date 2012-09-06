#!/bin/sh

set -e

EIDETICKER=$(dirname $0)/../

if [ -z $NUM_RUNS ]; then
    NUM_RUNS=5
fi

if [ -z $EXPIRY_THRESHOLD ]; then
    EXPIRY_THRESHOLD=3
fi

if [ $# -gt 0 ]; then
    TESTS=$@
else
    if [ -z $TESTS ]; then
        # Default set of tests
        TESTS="clock taskjs nightly cnn nytimes-scroll nytimes-zoom reddit wikipedia imgur"
    fi
fi

export PATH=$PATH:$HOME/tools/android-sdk-linux/tools:$HOME/tools/android-sdk-linux/platform-tools:$HOME/bin:$HOME/.local/bin

cd $EIDETICKER
. bin/activate

# Expire old captures/videos
./bin/expire.py --max-age $EXPIRY_THRESHOLD

# Update apps on the phone to the latest
./bin/update-phone.py

for TEST in $TESTS; do
  # Clean out /tmp/eideticker directory (in case there are any artifacts
  # from unsuccessful runs kicking around)
  rm -rf /tmp/eideticker/*
  echo "Running $TEST"
  ./bin/update-dashboard.py --product nightly --num-runs $NUM_RUNS $TEST src/dashboard
done
