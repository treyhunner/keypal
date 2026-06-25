import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median

from fsrs import Card, Rating, ReviewLog, Scheduler

from keypal.models import Pack, Shortcut

FAST_MS = 2_000
SLOW_MS = 8_000
DEFAULT_NEW_PER_SESSION = 5

SANITY_MAX_TIMING_MS = 180_000

RECENT_REVIEWS_FOR_PACE = 60
MIN_REVIEWS_FOR_PACE = 5
INTER_CARD_OVERHEAD_MS = 3_000
COLD_START_MS_PER_CARD = 8_000
MIN_MS_PER_CARD = 2_000
MAX_MS_PER_CARD = 60_000
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


def get_thresholds(
    signals: Iterable[dict],
    defaults: Thresholds = DEFAULT_THRESHOLDS,
) -> Thresholds:
    response_times = [s.get("response_time_ms") for s in signals]
    n = len(
        [
            rt
            for rt in response_times
            if rt is not None and 0 <= rt <= SANITY_MAX_TIMING_MS
        ]
    )
    if n < PERSONAL_MIN_REVIEWS:
        return defaults
    personal = compute_personal_thresholds(response_times)
    if personal is None:
        return defaults
    if n >= PERSONAL_FULL_REVIEWS:
        return personal
    weight = (n - PERSONAL_MIN_REVIEWS) / (PERSONAL_FULL_REVIEWS - PERSONAL_MIN_REVIEWS)
    return blend_thresholds(defaults, personal, weight)


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
    session = due + new[:new_per_session]
    random.shuffle(session)
    return session


def apply_assessment(
    results: list[tuple[str, bool]],
    current_disabled: set[str],
) -> set[str]:
    """Compute the new disabled set after an assessment.

    results: list of (shortcut_id, was_correct) pairs.
    Returns the updated disabled set: correct and rejected items are disabled,
    kept items are enabled (even if previously disabled).
    """
    new_disabled = set(current_disabled)
    for sid, correct in results:
        if correct:
            new_disabled.add(sid)
        else:
            new_disabled.discard(sid)
    return new_disabled


def reject_from_assessment(
    disabled: set[str],
    rejected_ids: set[str],
) -> set[str]:
    """After triage, disable rejected shortcuts."""
    return disabled | rejected_ids


def select_multi_session(
    packs: Sequence[Pack],
    cards: Mapping[str, Card],
    *,
    new_per_session: int = DEFAULT_NEW_PER_SESSION,
    now: datetime | None = None,
    disabled: set[str] | None = None,
    seen: set[str] | None = None,
) -> list[tuple[Shortcut, Pack]]:
    now = now or datetime.now(timezone.utc)
    disabled = disabled or set()
    seen = seen or set()
    due: list[tuple[Shortcut, Pack]] = []
    new: list[tuple[Shortcut, Pack]] = []
    collected_ids: set[str] = set()
    for pack in packs:
        for shortcut in pack.shortcuts:
            sid = pack.shortcut_id(shortcut)
            if sid in disabled or sid in collected_ids:
                continue
            collected_ids.add(sid)
            card = cards.get(sid)
            is_shared_other = bool(
                shortcut.shared_id
            ) and not shortcut.shared_id.startswith(f"{pack.id}:")
            unseen_in_pack = f"{pack.id}::{sid}" not in seen
            if card is None:
                new.append((shortcut, pack))
            elif card.due is None or card.due <= now:
                due.append((shortcut, pack))
            elif is_shared_other and unseen_in_pack:
                new.append((shortcut, pack))
    session = due + new[:new_per_session]
    random.shuffle(session)
    return session


def ms_per_card(response_times: Iterable[int | None]) -> int:
    """Median response time plus inter-card overhead, with cold-start fallback."""
    sane = [
        t for t in response_times if t is not None and 0 < t <= SANITY_MAX_TIMING_MS
    ]
    recent = sane[-RECENT_REVIEWS_FOR_PACE:]
    if len(recent) < MIN_REVIEWS_FOR_PACE:
        return COLD_START_MS_PER_CARD
    raw = int(median(recent)) + INTER_CARD_OVERHEAD_MS
    return max(MIN_MS_PER_CARD, min(MAX_MS_PER_CARD, raw))


def estimate_session_seconds(
    n_cards: int,
    response_times: Iterable[int | None],
) -> int:
    """Estimated seconds for a session of n_cards."""
    if n_cards <= 0:
        return 0
    return round(n_cards * ms_per_card(response_times) / 1000)


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"~{seconds} sec"
    minutes = round(seconds / 60)
    return f"~{max(1, minutes)} min"
