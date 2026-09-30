from flake import memory
from flake.risk.backtest import total

GROUP_ID = "friends"

ALTERNATIVES = [
    ("nobody", []),
    ("sam only", ["sam"]),
    ("sam+maya", ["sam", "maya"]),
    ("sam+maya+priya", ["sam", "maya", "priya"]),
    ("everyone", ["sam", "priya", "jordan", "maya"]),
]


def rules_for(people):
    if not people:
        return []
    return [{"type": "book_refundable_for", "people": sorted(people)}]


def main():
    episodes = memory.resolved_episodes(GROUP_ID)

    header = f"{'refundable set':<16}{'cost':>10}"
    print(f"{len(episodes)} resolved plans")
    print(header)
    print("-" * len(header))
    for label, people in ALTERNATIVES:
        print(f"{label:<16}{total(rules_for(people), episodes):>10.2f}")


if __name__ == "__main__":
    main()
