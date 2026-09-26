# Flake data model (frozen)

Shared contract for all three lanes. Change here first, then in code.

## `episodes` (Lane A writes, Lane B/C read)

```
_id                 str    "ep_006"
group_id            str
title, kind         str
day                 str
day_type            str    weekday | weekend
cost_per_person_usd number
min_people          int
version_id          str    harness_versions._id this plan ran under
status              str    proposed -> booked -> resolved
created_at, resolved_at   datetime

rsvps                list[{person: str, rsvp: "yes"|"no"}]

booking:
  non_refundable_for list[str]
  refundable_for     list[str]
  deposit_usd        number
  premium_usd        number

money_requests       list[{id, person, amount_usd, upfront: bool, at: datetime}]
approvals            list[{tool: str, at: datetime}]

outcomes:                        # written by the world simulator after resolution
  showed              list[str]
  bailed              list[str]
  paid_late_days      dict[str, int]
  lost_nonrefundable_usd number
  premium_paid_usd    number
  total_cost_usd      number

summary              str
embedding            list[float]   # 1536-dim, text-embedding-3-small
```

## `harness_versions` (Lane C owns lifecycle; Lane B writes `backtest`)

```
_id          str   "{group_id}:v{version}"
group_id     str
version      int
parent       str | null            # _id of the version this superseded/rolled back from
status       str   candidate | rejected | canary | active | rolled_back | superseded
created_by   str
created_at   datetime
rationale    str                   # LLM's explanation

policy: {                          # what the gate actually reads -- one nested dict
  rules: list[{
    id: str, type: str, people: list[str], reason: str, evidence: list[str]  # episode ids
  }]
  # type one of: book_refundable_for, require_deposit_from, auto_collect_from,
  #              avoid_day_type, max_plan_cost_usd

  guardrails: {
    max_nonrefundable_exposure_usd: int,
    max_auto_spend_usd: int,
    min_expected_attendance_ratio: float,
    min_confidence: float,
  }
  # clamped to flake.harness.constitution.FLOORS at creation time (harness/versions.create)

  tool_permissions: {
    send_message: auto|ask|deny,
    propose_plan: auto|ask|deny,
    poll_rsvps:   auto|ask|deny,
    book: { refundable: auto|ask|deny, non_refundable: auto|ask|deny },
    request_money: { default: ask|auto, auto_for: list[str] },
    cancel_booking: ask|deny,       # constitution always forces this to "ask"
    ask_organizer: auto,            # constitution never lets this be denied
    finish_plan: auto,              # constitution never lets this be denied
  }

  context_policy: { similar_plans_k: int, notes_per_person: int, include_recent_bails: bool }
  model: str
}

backtest: { episodes: list[str], baseline_usd, proposed_usd, delta_usd, accepted: bool, rejected: bool } | null
constitution_notes: list[str]        # what got clamped, for the demo/audit trail
canary: { episode_id, expected_cost_usd, realized_cost_usd, result: promoted|rolled_back } | null
```

## `risk_profiles` (Lane B owns)

```
_id        str   "{group_id}:{person}"
person     str
group_id   str
flake:     { n, k, alpha, beta, p_mean, p_upper90, credibility }
pay_late:  { n, k, alpha, beta, p_mean, p_upper90, credibility }
flake_score int   # 850 - 550 * p_mean
by_day_type dict | null
updated_at datetime
```

## `audit_log` (Lane C owns)

```
_id            str   "ad_NNN"  (zero-padded incrementing counter)
episode_id     str
version_id     str   harness_versions._id in effect for this call
tool           str
requested_args dict
final_args     dict
decision       str   allow | modify | ask | deny
rule_id        str | null
reason         str
ts             datetime
```

## Lane A's 7 tools

`propose_plan`, `poll_rsvps`, `book`, `request_money`, `send_message`, `ask_organizer`, `finish_plan`

## Other collections

`groups`, `notes`, `checkpoints`, `checkpoint_writes` (LangGraph checkpointer, auto-created), `chat_log`.
