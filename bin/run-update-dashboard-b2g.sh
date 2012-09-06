#!/bin/sh

set -e

EIDETICKER=$(dirname $0)/../
TESTS="clock taskjs nightly cnn nytimes-scroll reddit wikipedia imgur"

if [ -z $NUM_RUNS ]; then
    echo "setting to 5"
    NUM_RUNS=5
fi


if [ -z $EXPIRY_THRESHOLD ]; then
    EXPIRY_THRESHOLD=3
fi

if [ $# -gt 0 ]; then
    TESTS=$@
fi

export PATH=$PATH:$HOME/tools/android-sdk-linux/tools:$HOME/tools/android-sdk-linux/platform-tools:$HOME/bin:$HOME/.local/bin

cd $EIDETICKER
. bin/activate

# Expire old captures/videos
./bin/expire.py --max-age $EXPIRY_THRESHOLD

for TEST in $TESTS; do
  # Clean out /tmp/eideticker directory (in case there are any artifacts
  # from unsuccessful runs kicking around)
  rm -rf /tmp/eideticker/*
  echo "Running $TEST"
  ./bin/update-dashboard.py --device-id Panda --product b2g --num-runs $NUM_RUNS $TEST src/dashboard
done
