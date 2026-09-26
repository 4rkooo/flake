from flake.world.people import PREMIUM_RATE


def refundable_people(rules):
    people = set()
    for rule in rules:
        if rule["type"] == "book_refundable_for":
            people.update(rule["people"])
    return people


def cost_under(rules, episode):
    share = episode["cost_per_person_usd"]
    yes = {r["person"] for r in episode.get("rsvps", []) if r["rsvp"] == "yes"}
    covered = refundable_people(rules)
    bailed = set(episode["outcomes"]["bailed"])
    return share * len(bailed - covered) + PREMIUM_RATE * share * len(yes & covered)


def total(rules, episodes):
    return sum(cost_under(rules, episode) for episode in episodes)


def _late_days(episode, person):
    return episode["outcomes"].get("paid_late_days", {}).get(person, 0)


def run(candidate, incumbent, episodes):
    base = total(incumbent, episodes)
    candidate_total = total(candidate, episodes)

    accepted = []
    rejected = []
    details = []
    for i, rule in enumerate(candidate):
        without = candidate[:i] + candidate[i + 1 :]
        marginal = total(without, episodes) - candidate_total

        detail = {
            "rule": rule["type"],
            "people": rule["people"],
            "delta_usd": marginal,
        }
        if rule["type"] == "require_deposit_from":
            detail["late_days_avoided"] = sum(
                _late_days(episode, person)
                for episode in episodes
                for person in rule["people"]
            )
        elif rule["type"] == "auto_collect_from":
            detail["on_time_payments"] = sum(
                1
                for episode in episodes
                for person in rule["people"]
                if person in episode["outcomes"].get("showed", [])
                and _late_days(episode, person) == 0
            )
        details.append(detail)

        if marginal < 0:
            rejected.append(rule)
        else:
            accepted.append(rule)

    proposed = total(accepted, episodes)
    delta = base - proposed
    return {
        "episodes": len(episodes),
        "baseline_usd": base,
        "proposed_usd": proposed,
        "delta_usd": delta,
        "decision": "ship" if delta > 0 else "reject",
        "accepted": accepted,
        "rejected": rejected,
        "details": details,
    }


def _print_run(label, result):
    print(f"\n{label}")
    print(f"  episodes:  {result['episodes']}")
    print(f"  baseline:  ${result['baseline_usd']:.2f}")
    print(f"  proposed:  ${result['proposed_usd']:.2f}")
    print(f"  delta:     ${result['delta_usd']:.2f}")
    print(f"  decision:  {result['decision']}")
    print(f"  accepted:  {len(result['accepted'])}  rejected: {len(result['rejected'])}")
    for detail in result["details"]:
        extras = ""
        if "late_days_avoided" in detail:
            extras = f"  late_days_avoided={detail['late_days_avoided']}"
        elif "on_time_payments" in detail:
            extras = f"  on_time_payments={detail['on_time_payments']}"
        people = ", ".join(detail["people"])
        print(f"    {detail['rule']} [{people}]: ${detail['delta_usd']:.2f}{extras}")


if __name__ == "__main__":
    from flake.config import db
    from flake.risk.pricing import propose_rules

    episodes = list(
        db.episodes.find({"group_id": "friends", "status": "resolved"}).sort("_id")
    )
    profiles = {
        doc["person"]: doc for doc in db.risk_profiles.find({"group_id": "friends"})
    }
    v2 = propose_rules(profiles, [], {})["rules"]

    header = f"{'plan':<16}{'share':>7}{'bailed':>13}{'v1':>9}{'v2':>9}{'saved':>9}"
    print(header)
    print("-" * len(header))
    for episode in episodes:
        v1_cost = cost_under([], episode)
        v2_cost = cost_under(v2, episode)
        bailed = ", ".join(episode["outcomes"]["bailed"]) or "-"
        print(
            f"{episode['title']:<16}{episode['cost_per_person_usd']:>7}{bailed:>13}"
            f"{v1_cost:>9.2f}{v2_cost:>9.2f}{v1_cost - v2_cost:>9.2f}"
        )

    _print_run("v2 vs v1", run(v2, [], episodes))
    _print_run("v3 (drop refundable rules) vs v2", run([], v2, episodes))
