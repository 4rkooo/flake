"""observe.py: no-op without subscribers, ordered delivery with one, quiet() suppression,
and cooperative cancellation at the next observation point."""
import threading

import pytest

from flake import observe


@pytest.fixture(autouse=True)
def clean():
    observe.clear_cancel()
    yield
    for fn in list(observe._subscribers):
        observe.unsubscribe(fn)
    observe.clear_cancel()


def test_emit_without_subscribers_is_a_no_op():
    observe.emit("anything", x=1)  # must not raise


def test_subscribers_receive_kind_and_fields_in_order():
    seen = []
    observe.subscribe(lambda kind, fields: seen.append((kind, fields)))
    observe.emit("a", n=1)
    observe.emit("b", n=2)
    assert seen == [("a", {"n": 1}), ("b", {"n": 2})]


def test_quiet_suppresses_this_thread_only():
    seen = []
    observe.subscribe(lambda kind, fields: seen.append(kind))
    with observe.quiet():
        observe.emit("hidden")
        t = threading.Thread(target=lambda: observe.emit("from-other-thread"))
        t.start(); t.join()
    observe.emit("visible")
    assert seen == ["from-other-thread", "visible"]


def test_a_failing_subscriber_does_not_break_the_caller():
    def bad(kind, fields):
        raise RuntimeError("viewer bug")
    observe.subscribe(bad)
    observe.emit("x")


def test_cancel_raises_at_the_next_observation_point():
    observe.request_cancel()
    with pytest.raises(observe.Cancelled):
        observe.emit("node.start")
    with observe.quiet():  # state reads keep working while a reset is in flight
        observe.emit("read")
    observe.clear_cancel()
    observe.emit("fine again")


def test_notes_are_per_thread_and_consumed_once():
    observe.note("llm_cache", "hit")
    assert observe.take("llm_cache") == "hit"
    assert observe.take("llm_cache", "off") == "off"
