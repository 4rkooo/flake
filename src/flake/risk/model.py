import random

from scipy.stats import beta as beta_dist

from flake.config import db, DEMO_SEED
from flake.risk.scores import flake_score
from flake.world.people import PEOPLE

PRIOR_ALPHA = 0.5
PRIOR_BETA = 1.5
K = 2.0


def posterior(n, k):
    alpha = PRIOR_ALPHA + k
    beta = PRIOR_BETA + (n - k)
    return {
        "n": n,
        "k": k,
        "alpha": alpha,
        "beta": beta,
        "p_mean": alpha / (alpha + beta),
        "p_upper90": float(beta_dist.ppf(0.90, alpha, beta)),
        "credibility": n / (n + K),
    }


def build_profiles(group_id, episodes):
    profiles = {}
    for person in PEOPLE:
        flake_n = flake_k = 0
        late_n = late_k = 0
        by_day_type = {}

        for episode in episodes:
            rsvps = {r["person"]: r["rsvp"] for r in episode.get("rsvps", [])}
            if rsvps.get(person) != "yes":
                continue

            outcomes = episode.get("outcomes", {})
            bailed = person in outcomes.get("bailed", [])
            day_counts = by_day_type.setdefault(episode["day_type"], {"n": 0, "k": 0})

            flake_n += 1
            day_counts["n"] += 1
            if bailed:
                flake_k += 1
                day_counts["k"] += 1
            else:
                late_n += 1
                if outcomes.get("paid_late_days", {}).get(person, 0) > 0:
                    late_k += 1

        flake_post = posterior(flake_n, flake_k)
        doc = {
            "_id": f"{group_id}:{person}",
            "group_id": group_id,
            "person": person,
            "flake": flake_post,
            "pay_late": posterior(late_n, late_k),
            "by_day_type": by_day_type,
            "flake_score": flake_score(flake_post["p_mean"]),
        }
        db.risk_profiles.replace_one({"_id": doc["_id"]}, doc, upsert=True)
        profiles[person] = doc

    return profiles


def attendance(profiles, yes_people, min_people, sims=1000):
    rng = random.Random(DEMO_SEED)
    show_probs = [1 - profiles[p]["flake"]["p_mean"] for p in yes_people]

    total = 0
    hit_min = 0
    for _ in range(sims):
        count = sum(1 for p in show_probs if rng.random() < p)
        total += count
        if count >= min_people:
            hit_min += 1

    return {
        "expected": total / sims,
        "p_at_least_min": hit_min / sims,
        "min_people": min_people,
    }


if __name__ == "__main__":
    episodes = list(db.episodes.find({"group_id": "taco-council", "status": "resolved"}))
    profiles = build_profiles("taco-council", episodes)

    header = (
        f"{'person':<8}{'flake':>10}{'p_mean':>9}{'p_up90':>9}"
        f"{'late':>10}{'p_mean':>9}{'p_up90':>9}{'score':>7}  by_day_type"
    )
    print(header)
    print("-" * len(header))
    for person, profile in profiles.items():
        flake = profile["flake"]
        late = profile["pay_late"]
        days = ", ".join(
            f"{day} {c['n']}/{c['k']}" for day, c in profile["by_day_type"].items()
        )
        flake_nk = f"{flake['n']}/{flake['k']}"
        late_nk = f"{late['n']}/{late['k']}"
        print(
            f"{person:<8}{flake_nk:>10}"
            f"{flake['p_mean']:>9.4f}{flake['p_upper90']:>9.4f}"
            f"{late_nk:>10}"
            f"{late['p_mean']:>9.4f}{late['p_upper90']:>9.4f}"
            f"{profile['flake_score']:>7}  {days}"
        )

    print()
    print(attendance(profiles, ["sam", "priya", "jordan", "maya"], 3))
