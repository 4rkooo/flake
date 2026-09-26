"""Outcomes arrive late, repeatably; rsvp, book, organizer_answer, resolve, tick -- owned by Lane B."""


def day_type(day: str) -> str:
    raise NotImplementedError("Lane B: weekday | weekend from a day string")


def tick(days: int) -> list[str]:
    raise NotImplementedError("Lane B: resolve booked plans whose time has passed, return their episode ids")
