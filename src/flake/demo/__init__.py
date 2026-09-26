"""
flake/demo  -- the presenter-controlled visual demo.

A FastAPI service that runs the existing script one beat at a time in a background
worker, turns the observe hooks into an ordered event journal for the browser (SSE),
and holds ask_organizer calls until the presenter clicks Approve or Decline.

Nothing in here is imported by the CLI. `uv run flake-demo` is the entry point.
"""
