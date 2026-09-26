from langchain_core.tools import tool
from flake import memory
from flake.world import simulator as world

@tool
def propose_plan(title: str, kind: str, day: str, cost_per_person_usd: int, min_people: int) -> str:
    """Create a plan for the group. kind is one of dinner, karaoke, trip, brunch, tickets.
    day is an ISO date. Returns the plan_id. Call this first, exactly once per plan."""
    plan_id = memory.create_episode(title=title, kind=kind, day=day,
                                    cost_per_person_usd=cost_per_person_usd, min_people=min_people)
    memory.chat("flake", f"Proposal: {title} on {day}, about ${cost_per_person_usd} each. Who's in?")
    return plan_id

@tool
def poll_rsvps(plan_id: str) -> list[dict]:
    """Ask everyone in the group whether they are in. Returns a list of {person, rsvp} with rsvp yes, no or maybe."""
    rsvps = world.rsvp(memory.get_episode(plan_id))
    memory.update_episode(plan_id, {"rsvps": rsvps})
    return rsvps

@tool
def book(plan_id: str, non_refundable_for: list[str], refundable_for: list[str]) -> dict:
    """Book the plan. Put each yes-RSVP person in exactly one list. Non-refundable costs nothing extra
    but their share is lost if they bail; refundable costs a 15% premium per person. Returns the receipt."""
    receipt = world.book(memory.get_episode(plan_id), non_refundable_for, refundable_for)
    memory.update_episode(plan_id, {"booking": receipt})
    return receipt

@tool
def request_money(plan_id: str, person: str, amount_usd: int, upfront: bool) -> str:
    """Ask one person to pay their share. upfront=True means before the booking, as a deposit."""
    request_id = memory.add_money_request(plan_id, person, amount_usd, upfront)
    memory.chat("flake", f"@{person} please send ${amount_usd}" + (" before I book." if upfront else "."))
    return request_id

@tool
def send_message(text: str) -> str:
    """Post a short message to the group chat."""
    memory.chat("flake", text)
    return "ok"

@tool
def ask_organizer(question: str, approve_tool: str = "") -> str:
    """Ask the organizer, a yes/no question when the policy requires approval. Returns the answer.
    approve_tool is filled in by the gate; leave it empty when you call this yourself."""
    answer = world.organizer_answer(question)
    if approve_tool and answer.lower().startswith("y"):
        memory.add_approval(memory.current_run["plan_id"], approve_tool)   # lets the gate allow the retry
    return answer

@tool
def finish_plan(plan_id: str, summary: str) -> str:
    """Call this when the booking is made and money is requested. summary is two sentences about what was decided and why."""
    memory.finish_episode(plan_id, summary)
    return "ok"

TOOLS = [propose_plan, poll_rsvps, book, request_money, send_message, ask_organizer, finish_plan]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}