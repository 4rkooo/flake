"""A reset stops a run at the observation point that saw it. No `except Exception` on the way
out may turn Cancelled into an ordinary tool error, an LLM fallback or a skipped index."""
import pytest
from langchain_core.messages import AIMessage

from flake import observe
from flake.world import simulator


@pytest.fixture(autouse=True)
def no_cancel_left_over():
    observe.clear_cancel()
    yield
    observe.clear_cancel()
    simulator.set_organizer(None)


def test_a_cancelled_approval_escapes_the_tool_node():
    # ToolNode turns tool failures into ToolMessages; a reset must not become one the model retries.
    # Pins the installed default (re-raise anything that is not a bad-arguments error).
    from langgraph.graph import START, MessagesState, StateGraph
    from flake.agent import graph

    def reset_while_waiting(question):
        raise observe.Cancelled("approval cancelled by reset")
    simulator.set_organizer(reset_while_waiting)
    only_tools = StateGraph(MessagesState)
    only_tools.add_node("tools", graph.tool_node)    # the plan graph's own ToolNode
    only_tools.add_edge(START, "tools")
    call = {"id": "c1", "name": "ask_organizer", "type": "tool_call",
            "args": {"question": "Approve book {}? Reason: probation", "approve_tool": "book"}}
    with pytest.raises(observe.Cancelled, match="approval cancelled"):
        only_tools.compile().invoke({"messages": [AIMessage(content="", tool_calls=[call])]})


def test_a_reset_during_the_wording_step_is_not_taken_for_a_network_failure(monkeypatch):
    from flake.agent import underwriter_llm

    class ResetMidCall:
        def with_structured_output(self, schema, **_):
            self.schema = schema
            return self

        def invoke(self, prompt):
            observe.request_cancel()                 # the presenter resets while the model answers
            return self.schema(rationale="words", reasons=[])

    monkeypatch.setattr(underwriter_llm, "llm", ResetMidCall())
    with pytest.raises(observe.Cancelled) as exc:
        underwriter_llm.propose({}, {}, [], {})
    assert str(exc.value) == "proposal.worded"       # stopped there, not by way of the fallback


def test_a_reset_while_waiting_on_an_index_is_not_reported_as_a_skipped_index(monkeypatch):
    from flake.demo import reset as reset_mod

    class Indexes:
        @staticmethod
        def main(timeout, progress):
            observe.request_cancel()                 # a second reset while Atlas builds the index
            progress("episodes.episodes_vec: PENDING, waiting")

    real = reset_mod.load_script
    monkeypatch.setattr(reset_mod, "load_script", lambda name: Indexes if name == "create_indexes" else real(name))
    with pytest.raises(observe.Cancelled) as exc:
        reset_mod.run(index_timeout=0)
    # the original Cancelled, not a second one raised while logging "index setup skipped"
    assert exc.value.__context__ is None
