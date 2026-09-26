"""The fixed script, one beat per row of the presentation table. The briefs are the
exact strings scripts/demo.sh passes to `flake plan`, so cached model calls replay."""

GROUP = "taco-council"

TACO_BRIEF = "Taco Tuesday: dinner next Tuesday, about $25 each, at least 3 people"
BEACH_BRIEF = "Beach weekend: Saturday trip in two weeks, $120 each, need at least 3"

BEATS = [
    {"id": "reset", "title": "Reset / baseline", "operation": "reset",
     "blurb": "Restore the five historical plans and v1 on probation; show the starting risk profiles and guardrails."},
    {"id": "taco", "title": "Taco Tuesday", "operation": "plan", "brief": TACO_BRIEF,
     "blurb": "Submit the $25 brief: retrieval, agent turns, gate checks, approvals, booking."},
    {"id": "tick1", "title": "Advance 7 days", "operation": "tick", "days": 7,
     "blurb": "Actual simulator outcomes: Sam's cancellation, incurred costs, episode updates."},
    {"id": "retro", "title": "Run Retro", "operation": "retro", "reckless": False,
     "blurb": "Updated risks, proposal rationale, constitution checks, backtest, v2's resulting status."},
    {"id": "compare", "title": "Compare policies", "operation": "compare",
     "blurb": "A structured v1 -> v2 comparison: rules, permissions, guardrails, context settings."},
    {"id": "beach", "title": "Beach Weekend", "operation": "plan", "brief": BEACH_BRIEF,
     "blurb": "Submit the $120 brief; v2 enters the gate and its learned rules shape the booking."},
    {"id": "tick2", "title": "Advance / evaluate", "operation": "tick", "days": 7,
     "blurb": "Realized cost against the incumbent's expected cost: promotion or rollback."},
    {"id": "reckless", "title": "Reckless Retro", "operation": "retro", "reckless": True,
     "blurb": "The deliberately bad proposal, its backtest, the rejection, and the policy history."},
]
