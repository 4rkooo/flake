#!/bin/sh
# each line is one beat; the narrator reads the demo chapter
# both retros backtest over every resolved plan, including the live ones, so their deltas will not be
# the guide's +/-$218 (5 seeded plans only): read the "backtest over N past plans" line off the screen
set -e
uv run python scripts/reset_demo.py
uv run flake versions
uv run flake plan "Taco Tuesday: dinner next Tuesday, about \$25 each, at least 3 people"
uv run flake tick 7
uv run flake retro
uv run flake diff v1 v2
uv run flake plan "Beach weekend: Saturday trip in two weeks, \$120 each, need at least 3"
uv run flake tick 7
uv run flake versions
uv run flake retro --reckless
uv run flake versions
