"""Beta-Binomial profiles, credibility, attendance Monte Carlo -- owned by Lane B."""


def build_profiles(group_id: str, episodes: list[dict]) -> dict:
    raise NotImplementedError("Lane B: one Beta-Binomial profile per friend from resolved episodes")


def attendance(risk: dict, yes: list[str], min_people: int) -> dict:
    raise NotImplementedError("Lane B: Monte Carlo P(at least min_people show)")
