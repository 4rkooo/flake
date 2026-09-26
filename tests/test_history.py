from datetime import date

from flake.world.history import GROUP_ID, HISTORY
from flake.world.people import ORGANIZER, PEOPLE


def test_five_resolved_episodes_for_the_demo_group():
    assert [e["_id"] for e in HISTORY] == [f"ep_00{i}" for i in range(1, 6)]
    assert all(e["group_id"] == GROUP_ID == "taco-council" for e in HISTORY)
    assert all(e["status"] == "resolved" for e in HISTORY)


def test_episodes_carry_the_schema_fields_readers_expect():
    for e in HISTORY:
        for key in ("kind", "min_people", "day_type", "rsvps", "booking", "outcomes", "summary"):
            assert key in e, f"{e['_id']} missing {key}"


def test_day_type_matches_the_calendar():
    for e in HISTORY:
        weekday = date.fromisoformat(e["day"]).weekday()
        assert e["day_type"] == {5: "saturday", 6: "sunday"}.get(weekday, "weekday")


def test_outcomes_add_up():
    for e in HISTORY:
        o = e["outcomes"]
        assert set(o["showed"]) | set(o["bailed"]) == set(PEOPLE)
        assert not set(o["showed"]) & set(o["bailed"])
        assert o["lost_nonrefundable_usd"] == e["cost_per_person_usd"] * len(o["bailed"])
        assert ORGANIZER in e["booking"]["non_refundable_for"]


if __name__ == "__main__":  # no pytest in the venv, so run the tests directly
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
