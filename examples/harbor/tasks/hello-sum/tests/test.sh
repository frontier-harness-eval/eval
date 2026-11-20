#!/bin/bash
# Harbor runs this inside the task container after the agent finishes.
# Whatever is written to /logs/verifier/reward.txt becomes the trial reward.
pass=1
check() { [ "$(/app/sum.sh "${@:2}")" = "$1" ] || { echo "FAIL: sum $* "; pass=0; }; }
[ -x /app/sum.sh ] || pass=0
check 15 2 3 10
check 0
check -4 1 -5
echo "$pass" > /logs/verifier/reward.txt
