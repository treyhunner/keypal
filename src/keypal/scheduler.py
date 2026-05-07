from fsrs import Card, Rating, ReviewLog, Scheduler

FAST_MS = 2_000
SLOW_MS = 8_000


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
