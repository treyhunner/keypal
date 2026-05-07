from collections.abc import Mapping
from datetime import datetime, timezone

from fsrs import Card, Rating, ReviewLog, Scheduler

from keypal.models import Pack, Shortcut

FAST_MS = 2_000
SLOW_MS = 8_000
DEFAULT_NEW_PER_SESSION = 5


def classify(correct: bool, response_time_ms: int) -> Rating:
    if not correct:
        return Rating.Again
    if response_time_ms < FAST_MS:
        return Rating.Easy
    if response_time_ms > SLOW_MS:
        return Rating.Hard
    return Rating.Good


def review(
    card: Card,
    *,
    correct: bool,
    response_time_ms: int,
    scheduler: Scheduler | None = None,
) -> tuple[Card, ReviewLog]:
    rating = classify(correct, response_time_ms)
    return (scheduler or Scheduler()).review_card(
        card, rating, review_duration=response_time_ms
    )


def review_with_rating(
    card: Card,
    rating: Rating,
    *,
    scheduler: Scheduler | None = None,
) -> tuple[Card, ReviewLog]:
    return (scheduler or Scheduler()).review_card(card, rating)


def select_session(
    pack: Pack,
    cards: Mapping[str, Card],
    *,
    new_per_session: int = DEFAULT_NEW_PER_SESSION,
    now: datetime | None = None,
) -> list[Shortcut]:
    now = now or datetime.now(timezone.utc)
    due: list[Shortcut] = []
    new: list[Shortcut] = []
    for shortcut in pack.shortcuts:
        card = cards.get(pack.shortcut_id(shortcut))
        if card is None:
            new.append(shortcut)
        elif card.due is None or card.due <= now:
            due.append(shortcut)
    return due + new[:new_per_session]
