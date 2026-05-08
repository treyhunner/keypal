from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from fsrs import Card, Rating, ReviewLog, Scheduler

from keypal.models import Pack, Shortcut

FAST_MS = 2_000
SLOW_MS = 8_000
DEFAULT_NEW_PER_SESSION = 5

SANITY_MAX_TIMING_MS = 180_000
PERSONAL_MIN_REVIEWS = 30
PERSONAL_FULL_REVIEWS = 100
PERSONAL_LOOKBACK_DAYS = 60
PERSONAL_PERCENTILE_FAST = 30
PERSONAL_PERCENTILE_SLOW = 90


@dataclass(frozen=True)
class Thresholds:
    fast_ms: int = FAST_MS
    slow_ms: int = SLOW_MS


DEFAULT_THRESHOLDS = Thresholds()


def _nearest_rank(sorted_values: list[int], percentile: int) -> int:
    n = len(sorted_values)
    idx = max(0, min(n - 1, round(percentile / 100 * (n - 1))))
    return sorted_values[idx]


def _sane_timings(values: Iterable[int | None]) -> list[int]:
    return sorted(v for v in values if v is not None and 0 <= v <= SANITY_MAX_TIMING_MS)


def compute_personal_thresholds(
    response_times: Iterable[int | None],
) -> Thresholds | None:
    rts = _sane_timings(response_times)
    if len(rts) < PERSONAL_MIN_REVIEWS:
        return None
    return Thresholds(
        fast_ms=_nearest_rank(rts, PERSONAL_PERCENTILE_FAST),
        slow_ms=_nearest_rank(rts, PERSONAL_PERCENTILE_SLOW),
    )


def blend_thresholds(
    absolute: Thresholds, personal: Thresholds, weight: float
) -> Thresholds:
    weight = max(0.0, min(1.0, weight))

    def lerp(a: int, p: int) -> int:
        return round(a + (p - a) * weight)

    return Thresholds(
        fast_ms=lerp(absolute.fast_ms, personal.fast_ms),
        slow_ms=lerp(absolute.slow_ms, personal.slow_ms),
    )


def classify(
    correct: bool,
    response_time_ms: int,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Rating:
    if not correct:
        return Rating.Again
    if response_time_ms < thresholds.fast_ms:
        return Rating.Easy
    if response_time_ms > thresholds.slow_ms:
        return Rating.Hard
    return Rating.Good


def review(
    card: Card,
    *,
    correct: bool,
    response_time_ms: int,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
    scheduler: Scheduler | None = None,
) -> tuple[Card, ReviewLog]:
    rating = classify(correct, response_time_ms, thresholds)
    return (scheduler or Scheduler()).review_card(
        card, rating, review_duration=response_time_ms
    )


def select_session(
    pack: Pack,
    cards: Mapping[str, Card],
    *,
    new_per_session: int = DEFAULT_NEW_PER_SESSION,
    now: datetime | None = None,
    disabled: set[str] | None = None,
    seen: set[str] | None = None,
) -> list[Shortcut]:
    now = now or datetime.now(timezone.utc)
    disabled = disabled or set()
    seen = seen or set()
    due: list[Shortcut] = []
    new: list[Shortcut] = []
    for shortcut in pack.shortcuts:
        sid = pack.shortcut_id(shortcut)
        if sid in disabled:
            continue
        card = cards.get(sid)
        is_shared_other = bool(
            shortcut.shared_id
        ) and not shortcut.shared_id.startswith(f"{pack.id}:")
        unseen_in_pack = f"{pack.id}::{sid}" not in seen
        if card is None:
            new.append(shortcut)
        elif card.due is None or card.due <= now:
            due.append(shortcut)
        elif is_shared_other and unseen_in_pack:
            # Shared with another pack and never reviewed in *this* pack: introduce it once.
            new.append(shortcut)
    return due + new[:new_per_session]
