from flake.world.people import PREMIUM_RATE

LOOSEN_MIN_N = 3
AUTO_COLLECT_MAX_UPPER = 0.30
DEPOSIT_MIN_UPPER = 0.50
RELIABLE_MAX_UPPER = 0.20
EXPOSURE_PER_RELIABLE = 75
AUTO_SPEND_PER_RELIABLE = 30


def reliable_people(risk):
    return sorted(
        person
        for person, profile in risk.items()
        if profile["flake"]["n"] >= LOOSEN_MIN_N
        and profile["flake"]["p_upper90"] < RELIABLE_MAX_UPPER
    )


def propose_rules(risk, losses, policy):
    rules = []

    # one rule for everyone whose expected loss beats the premium, so the gate
    # and audit log cite a single r1 (the guide's v2 shape)
    refundable = [p for p in sorted(risk) if risk[p]["flake"]["p_mean"] > PREMIUM_RATE]
    if refundable:
        quoted = ", ".join(f"{p} {risk[p]['flake']['p_mean']:.0%}" for p in refundable)
        rules.append(
            {
                "type": "book_refundable_for",
                "people": refundable,
                "reason": f"expected loss above the {PREMIUM_RATE:.0%} premium: {quoted}",
            }
        )
    refundable_count = len(refundable)

    deposit = []
    auto_collect = []
    for person in sorted(risk):
        late = risk[person]["pay_late"]
        if late["n"] < LOOSEN_MIN_N:
            continue
        if late["p_upper90"] > DEPOSIT_MIN_UPPER:
            deposit.append(person)
        if late["p_upper90"] < AUTO_COLLECT_MAX_UPPER:
            auto_collect.append(person)

    if deposit:
        quoted = ", ".join(
            f"{person} {risk[person]['pay_late']['p_upper90']:.0%}" for person in deposit
        )
        rules.append(
            {
                "type": "require_deposit_from",
                "people": deposit,
                "reason": (
                    f"late-payment upper bound above {DEPOSIT_MIN_UPPER:.0%}: {quoted}"
                ),
            }
        )

    if auto_collect:
        rules.append(
            {
                "type": "auto_collect_from",
                "people": auto_collect,
                "reason": (
                    f"late-payment upper bound below {AUTO_COLLECT_MAX_UPPER:.0%} "
                    f"on at least {LOOSEN_MIN_N} plans"
                ),
            }
        )

    reliable = reliable_people(risk)
    exposure = 25 * round(EXPOSURE_PER_RELIABLE * len(reliable) / 25)

    return {
        "rules": rules,
        "guardrails": {
            "max_nonrefundable_exposure_usd": exposure,
            "max_auto_spend_usd": AUTO_SPEND_PER_RELIABLE * len(reliable),
            "min_expected_attendance_ratio": 0.8,
            "min_confidence": 0.85,
        },
        "auto_book_nonrefundable": len(reliable) >= 2,
        "similar_plans_k": 3,
        "rationale": (
            f"{len(reliable)} reliable, {refundable_count} needing refundable booking, "
            f"{len(deposit)} needing a deposit, {len(auto_collect)} on auto-collect; "
            f"non-refundable exposure capped at ${exposure}."
        ),
    }


if __name__ == "__main__":
    import json

    from flake.config import db

    risk = {
        doc["person"]: doc for doc in db.risk_profiles.find({"group_id": "taco-council"})
    }
    print(json.dumps(propose_rules(risk, [], {}), indent=2))
    print(f"reliable: {reliable_people(risk)}")
