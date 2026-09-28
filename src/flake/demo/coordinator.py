"""The demo coordinator: runs the script one beat at a time in a background worker, turns
observe calls into journal events, holds ask_organizer until the presenter answers, and
resets cooperatively.

One operation at a time is deliberate: the plan loop uses a global current_run and
sequential plan ids, so two plans must never overlap. HTTP handlers only read state and
flip flags; all work happens on the worker thread."""

import ast
import re
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime

from flake import observe
from flake.demo import compare as compare_mod
from flake.demo import events as translate_mod
from flake.demo import reset as reset_mod
from flake.demo.beats import BEATS, GROUP
from flake.demo.journal import Journal, now


class Busy(Exception):
    """An operation is running or an approval is pending."""


class Blocked(Exception):
    """The script cannot advance from here (failed beat, or finished) without a reset."""


class ResetTimeout(Exception):
    """The worker did not stop in time; nothing was cleared."""


@dataclass
class Approval:
    id: str
    question: str
    tool: str | None
    args: dict
    reason: str | None
    plan_id: str | None
    version_id: str | None
    created_at: str
    event: threading.Event = field(default_factory=threading.Event, repr=False)
    decision: str | None = None      # approve | decline | cancelled
    answered_at: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "question": self.question, "tool": self.tool, "args": self.args, "reason": self.reason,
                "plan_id": self.plan_id, "version_id": self.version_id, "created_at": self.created_at,
                "decision": self.decision, "answered_at": self.answered_at}


def parse_question(question: str) -> tuple[str | None, dict, str | None]:
    # the gate phrases asks as "Approve <tool> <args>? Reason: <why>"
    m = re.match(r"^Approve (\w+) (\{.*\})\? Reason: (.*)$", question or "", re.S)
    if not m:
        return None, {}, None
    try:
        args = ast.literal_eval(m.group(2))
    except (ValueError, SyntaxError):
        args = {}
    return m.group(1), args if isinstance(args, dict) else {}, m.group(3).strip()


def jsonable(value):
    # Plain JSON for the browser, not bson.json_util's extended JSON: the UI uses _id values as
    # React keys and display text, so an ObjectId must arrive as its hex string, not {"$oid": ...}.
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


# Presentation pace: how long each kind of moment stays on screen before the worker moves on,
# in seconds at pace 1.0 (a plan beat takes about two minutes). Cached model calls finish a beat in
# a second or two, which is too fast to follow; these pauses turn the same run into something the eye can track. The presenter can
# scale them live (slow / normal / fast / instant); tests run at 0.
PACE = {
    "beat.start": 1.5, "node.start": 1.0, "llm.turn": 2.0, "llm.cache": 0.3, "gate.decision": 2.5, "tool.result": 1.5,
    "policy.loaded": 2.5, "context.built": 2.0, "memory.similar": 2.0, "memory.notes": 1.0, "memory.embedded": 1.0,
    "episode.created": 1.0, "chat.message": 1.0, "approval.resolved": 1.0, "plan.recorded": 1.5, "plan.end": 1.5,
    "sim.resolved": 3.0, "sim.tick": 1.0, "canary.evaluated": 3.0, "canary.skipped": 1.0,
    "retro.start": 2.0, "risk.profiles": 3.0, "proposal.pricing": 2.0, "proposal.worded": 2.0, "proposal.fallback": 2.0,
    "retro.proposal": 2.5, "backtest.run": 3.0, "version.created": 2.5, "version.status": 1.5, "retro.done": 1.5,
    "policy.compared": 1.0, "reset.step": 0.3, "reset.done": 1.0, "db.op": 0.12, "checkpoint.saved": 0.3,
}
MAX_PACE = 5.0

# where the learning loop's steps sit on the diagram, for the db rows they cause
LEARNING_NODE = {"retro.start": "risk", "risk.profiles": "risk", "retro.proposal": "proposal", "proposal.pricing": "proposal",
                 "proposal.worded": "proposal", "proposal.fallback": "proposal", "backtest.run": "backtest",
                 "version.created": "policy", "version.status": "policy", "canary.evaluated": "policy",
                 "canary.skipped": "policy", "retro.done": "policy", "sim.tick": "outcomes", "sim.resolved": "outcomes",
                 "policy.compared": "policy"}


class Coordinator:
    JOIN_TIMEOUT_S = 120

    def __init__(self, journal: Journal | None = None, watcher=None, reset_index_timeout: float | None = None,
                 pace: float = 0.0):
        self.journal = journal or Journal()
        self.watcher = watcher
        self.reset_index_timeout = reset_index_timeout
        self.pace = pace
        self._lock = threading.RLock()          # guards the fields below; never held while waiting
        self._control = threading.Lock()        # serialises presenter controls (next/reset) end to end
        self._worker: threading.Thread | None = None
        self.beat_index = -1            # -1: nothing has run in this server session
        self.beat_status = "idle"       # idle | running | done | error | cancelled
        self.beat_error: str | None = None
        self.beat_warning: str | None = None
        self.approvals: dict[str, Approval] = {}
        self._approval_seq = 0
        self.current_node: str | None = None
        self.current_plan_id: str | None = None
        self.current_version_id: str | None = None
        self._last_ask: dict | None = None
        self.last_reset_at: str | None = None

        observe.subscribe(self._on_observe)
        from flake.world import simulator
        simulator.set_organizer(self._organizer)

    def close(self) -> None:
        observe.unsubscribe(self._on_observe)
        from flake.world import simulator
        simulator.set_organizer(None)

    # ------------------------------------------------------------------ presenter controls
    def busy(self) -> bool:
        w = self._worker
        return bool(w and w.is_alive())

    def pending_approvals(self) -> list[dict]:
        with self._lock:
            return [a.to_dict() for a in self.approvals.values() if a.decision is None]

    def next_beat(self) -> dict:
        with self._control:
            with self._lock:
                if self.busy():
                    raise Busy("an operation is still running")
                if self.pending_approvals():
                    raise Busy("waiting for the presenter to approve or decline")
                if self.beat_status == "error":
                    raise Blocked("the last beat failed part-way; reset the demo to continue")
                first = self.beat_index < 0
                nxt = self.beat_index + 1
                if not first and nxt >= len(BEATS):
                    raise Blocked("the script is finished; reset to run it again")
            if first:
                return self._reset()            # the first beat is the baseline
            with self._lock:
                self._start(nxt)
                return self._beat_info()

    def reset(self) -> dict:
        with self._control:
            return self._reset()

    def _reset(self) -> dict:
        self._stop_worker()                     # cooperative; raises ResetTimeout if it will not stop
        with self._lock:
            session = self.journal.reset()      # new identity: late events cannot reach the new view
            self.approvals.clear()
            self._last_ask = None
            self.current_node = self.current_plan_id = self.current_version_id = None
            self.beat_status, self.beat_error, self.beat_warning = "idle", None, None
            self.last_reset_at = now()
            self._start(0)
            return {"session": session, **self._beat_info()}

    def set_pace(self, factor: float) -> float:
        if not (0 <= factor <= MAX_PACE):
            raise ValueError(f"pace must be between 0 and {MAX_PACE}")
        self.pace = float(factor)          # read at every pause, so it applies mid-beat
        return self.pace

    def _pause(self, kind: str) -> None:
        # hold the moment on screen; a reset request ends the wait early (the run then stops at its next hook)
        delay = PACE.get(kind, 0.0) * self.pace
        if delay <= 0:
            return
        deadline = time.monotonic() + delay
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or observe.cancel_requested():
                return
            time.sleep(min(0.1, remaining))

    def answer_approval(self, approval_id: str, decision: str) -> dict:
        if decision not in ("approve", "decline"):
            raise ValueError("decision must be approve or decline")
        with self._lock:
            ap = self.approvals[approval_id]           # KeyError -> 404 upstream
            if ap.decision is not None:
                # a second click or a stale tab: harmless, nothing changes
                return {"status": "already_answered", **ap.to_dict()}
            ap.decision, ap.answered_at = decision, now()
            ap.event.set()
            return {"status": "accepted", **ap.to_dict()}

    # ------------------------------------------------------------------ state for the browser
    def _beat_info(self) -> dict:
        beat = BEATS[self.beat_index] if 0 <= self.beat_index < len(BEATS) else None
        return {"index": self.beat_index, "id": beat["id"] if beat else None, "title": beat["title"] if beat else None,
                "operation": beat["operation"] if beat else None, "status": self.beat_status,
                "error": self.beat_error, "warning": self.beat_warning}

    def state(self) -> dict:
        from flake.config import db
        from flake.harness import versions

        with observe.quiet():
            history = versions.history(GROUP)
            profiles = {d["person"]: d for d in db.risk_profiles.find({"group_id": GROUP})}
            episodes = list(db.episodes.find({"group_id": GROUP}, {"embedding": 0}).sort("created_at", 1))
            audit = list(db.audit_log.find({}).sort("ts", 1).limit(500))
            chat = list(db.chat_log.find({"group_id": GROUP}).sort("at", 1))
            group = db.groups.find_one({"_id": GROUP})
        active = next((v for v in history if v["status"] == "active"), None)
        canary = next((v for v in history if v["status"] == "canary"), None)
        compares = [compare_mod.compare_policies(a, b) for a, b in zip(history, history[1:])]

        with self._lock:
            beat = self._beat_info()
            pending = self.pending_approvals()
            next_available = (not self.busy() and not pending and self.beat_status != "error"
                              and self.beat_index + 1 < len(BEATS))
            return jsonable({
                "session": self.journal.session,
                "cursor": self.journal.cursor(),
                "pace": self.pace,
                "needs_reset": self.beat_index < 0 or self.beat_status == "error",
                "busy": self.busy(),
                "beat": beat,
                "beats": [{"index": i, **{k: b[k] for k in ("id", "title", "operation", "blurb")}} for i, b in enumerate(BEATS)],
                "next_available": next_available,
                "next_title": BEATS[self.beat_index + 1]["title"] if self.beat_index + 1 < len(BEATS) else None,
                "pending_approvals": pending,
                "approvals": [a.to_dict() for a in self.approvals.values()],
                "group": group,
                "policy": {"active": active, "canary": canary, "effective": canary or active, "versions": history},
                "risk_profiles": profiles,
                "episodes": episodes,
                "audit": audit,
                "chat_log": chat,
                "compares": compares,
                "last_reset_at": self.last_reset_at,
                "events": [e.to_dict() for e in self.journal.all()],
            })

    # ------------------------------------------------------------------ worker
    def _start(self, index: int) -> None:
        observe.clear_cancel()
        self.beat_index, self.beat_status, self.beat_error, self.beat_warning = index, "running", None, None
        self._worker = threading.Thread(target=self._run, args=(index,), name=f"flake-beat-{index}", daemon=True)
        self._worker.start()

    def _stop_worker(self) -> None:
        # Called without self._lock held: the worker needs it to record its own cancellation.
        w = self._worker
        if w and w.is_alive():
            observe.request_cancel()            # the run raises Cancelled at its next observation point
            with self._lock:
                for ap in self.approvals.values():
                    if ap.decision is None:     # release anyone waiting on Alex
                        ap.decision, ap.answered_at = "cancelled", now()
                        ap.event.set()
            w.join(self.JOIN_TIMEOUT_S)
            if w.is_alive():
                raise ResetTimeout("the running operation did not stop in time; nothing was cleared, try again")
        observe.clear_cancel()

    def _run(self, index: int) -> None:
        beat = BEATS[index]
        op = beat["operation"]
        status, error, warning, stage = "done", None, None, op
        self._record("beat.start", index=index, beat=beat)
        try:
            if op == "reset":
                kwargs = {"index_timeout": self.reset_index_timeout} if self.reset_index_timeout is not None else {}
                reset_mod.run(**kwargs)
            elif op == "plan":
                from flake.agent.graph import run_plan
                ep = run_plan(GROUP, beat["brief"])
                if not ep.get("booking"):
                    reason = ep.get("incomplete_reason") or "no booking receipt"
                    if "turn limit" in reason or "never proposed" in reason:
                        stage = "agent"
                        raise RuntimeError(f"{ep['_id']} was not booked: {reason}")
                    warning = f"{ep['_id']} ended without a booking: {reason}"
            elif op == "tick":
                from flake import memory
                from flake.harness import canary
                from flake.world import simulator
                # each `flake tick` is its own process and rolls from a fresh DEMO_SEED; this server
                # ticks twice in one process (and again after a reset), so reseed to get the same draws
                simulator.rng.seed(simulator.DEMO_SEED)
                resolved = simulator.tick(beat["days"])
                stage = "canary"
                for plan_id in resolved:
                    canary.evaluate(GROUP, memory.get_episode(plan_id))
                if not resolved:
                    warning = "nothing was booked, so nothing resolved"
            elif op == "retro":
                from flake.harness import retro
                retro.run(GROUP, retro.RECKLESS if beat.get("reckless") else None)
            elif op == "compare":
                from flake.harness import versions
                history = versions.history(GROUP)
                by_n = {v["version"]: v for v in history}
                a, b = by_n.get(1), by_n.get(2)
                if a is None or b is None:
                    if len(history) < 2:
                        raise RuntimeError("two policy versions are needed to compare; run the Retro first")
                    a, b = history[-2], history[-1]
                self._record("policy.compared", compare=compare_mod.compare_policies(a, b), version_id=b["_id"])
            else:
                raise RuntimeError(f"unknown operation {op}")
        except observe.Cancelled:
            status = "cancelled"
            self._record("beat.cancelled", index=index, beat=beat)
        except Exception as e:  # noqa: BLE001 -- the stage is reported, progression stops
            status, error = "error", f"{type(e).__name__}: {e}"
            self._record("beat.error", index=index, beat=beat, stage=stage, error=error,
                         traceback=traceback.format_exc()[-2000:])
        else:
            self._record("beat.done", index=index, beat=beat, warning=warning)
        finally:
            with self._lock:
                last_node = self.current_node
            if self.watcher:
                self.watcher.flush_checkpoints(last_node)
            with self._lock:
                self.beat_status, self.beat_error, self.beat_warning = status, error, warning
                self.current_node = None

    # ------------------------------------------------------------------ the presenter as Alex
    def _organizer(self, question: str) -> str:
        tool, args, reason = parse_question(question)
        with self._lock:
            ask = self._last_ask or {}
            self._approval_seq += 1
            ap = Approval(id=f"ap_{self._approval_seq:03d}", question=question, tool=tool or ask.get("tool"),
                          args=args or ask.get("args") or {}, reason=reason or ask.get("reason"),
                          plan_id=self.current_plan_id, version_id=self.current_version_id, created_at=now())
            self.approvals[ap.id] = ap
            self._last_ask = None
        self._record("approval.requested", approval_id=ap.id, question=question, tool=ap.tool, args=ap.args,
                     reason=ap.reason, plan_id=ap.plan_id, version_id=ap.version_id)
        # hold the tool call here; the HTTP side stays responsive, the graph waits
        while not ap.event.wait(0.25):
            if observe.cancel_requested():
                break
        if ap.decision not in ("approve", "decline"):
            raise observe.Cancelled("approval cancelled by reset")
        self._record("approval.resolved", approval_id=ap.id, decision=ap.decision, tool=ap.tool,
                     plan_id=ap.plan_id, version_id=ap.version_id)
        return "yes" if ap.decision == "approve" else "no"

    # ------------------------------------------------------------------ observe -> journal
    def _on_observe(self, kind: str, fields: dict) -> None:
        # Runs on the worker and on ToolNode's tool threads (a batch of calls runs in parallel), so
        # the fields move under the lock; the checkpoint flush and _record's pause happen outside it.
        flush, flush_node = False, None
        with self._lock:
            if kind == "node.start":
                flush, flush_node = True, self.current_node     # the saver wrote after the previous node
                self.current_node = translate_mod.NODE_FOR_GRAPH.get(fields.get("node"))
            elif kind == "plan.start":
                self.current_plan_id, self.current_version_id = fields.get("plan_id"), None
            elif kind == "policy.loaded":
                self.current_version_id = fields.get("version_id")
            elif kind == "plan.end":
                flush, flush_node = True, self.current_node
                self.current_node = None
            elif kind == "gate.decision" and fields.get("decision") == "ask":
                self._last_ask = {"tool": fields.get("tool"), "args": fields.get("requested_args"),
                                  "reason": fields.get("reason"), "rule_id": fields.get("rule_id")}
            elif kind in LEARNING_NODE:
                self.current_node = LEARNING_NODE[kind]
            elif kind.startswith("reset."):
                self.current_node = None
        if flush and self.watcher:
            self.watcher.flush_checkpoints(flush_node)
        self._record(kind, **fields)

    def _record(self, kind: str, **fields) -> None:
        row = translate_mod.translate(kind, fields)
        with self._lock:
            node = row["node"]
            if node is None and kind in ("db.op", "db.failed"):
                node = self.current_node
            beat = BEATS[self.beat_index] if 0 <= self.beat_index < len(BEATS) else None
            plan_id = row.get("plan_id") or self.current_plan_id
            version_id = row.get("version_id") or self.current_version_id
        self.journal.append(kind, row["status"], beat=self.beat_index if beat else None,
                            beat_id=beat["id"] if beat else None, operation=beat["operation"] if beat else None,
                            node=node, summary=row["summary"], details=row["details"],
                            plan_id=plan_id, version_id=version_id)
        self._pause(kind)
