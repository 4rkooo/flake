#!/bin/sh
# each line is one beat; the narrator reads the demo chapter
set -e
python scripts/reset_demo.py
flake versions
flake plan "Taco Tuesday: dinner next Tuesday, about \$25 each, at least 3 people"
flake tick 7
flake retro
flake diff v1 v2
flake plan "Beach weekend: Saturday trip in two weeks, \$120 each, need at least 3"
flake tick 7
flake versions
flake retro --reckless
flake versions
