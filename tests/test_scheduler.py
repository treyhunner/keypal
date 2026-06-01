from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating

from keypal.models import Pack, Shortcut
from keypal.scheduler import (
    DEFAULT_THRESHOLDS,
    FAST_MS,
    PERSONAL_FULL_REVIEWS,
    PERSONAL_MIN_REVIEWS,
    SLOW_MS,
    Thresholds,
    apply_assessment,
    blend_thresholds,
    classify,
    compute_personal_thresholds,
    get_thresholds,
    reject_from_assessment,
    review,
    select_multi_session,
    select_session,
)


def test_classify_incorrect_is_again():
    assert classify(correct=False, response_time_ms=500) == Rating.Again
    assert classify(correct=False, response_time_ms=10_000) == Rating.Again


def test_classify_fast_correct_is_easy():
    assert classify(correct=True, response_time_ms=FAST_MS - 1) == Rating.Easy


def test_classify_medium_correct_is_good():
    assert classify(correct=True, response_time_ms=FAST_MS) == Rating.Good
    assert classify(correct=True, response_time_ms=SLOW_MS) == Rating.Good


def test_classify_slow_correct_is_hard():
    assert classify(correct=True, response_time_ms=SLOW_MS + 1) == Rating.Hard


def test_classify_with_custom_thresholds():
    fast = Thresholds(fast_ms=1_000, slow_ms=5_000)
    assert classify(correct=True, response_time_ms=999, thresholds=fast) == Rating.Easy
    assert (
        classify(correct=True, response_time_ms=1_000, thresholds=fast) == Rating.Good
    )
    assert (
        classify(correct=True, response_time_ms=5_000, thresholds=fast) == Rating.Good
    )
    assert (
        classify(correct=True, response_time_ms=5_001, thresholds=fast) == Rating.Hard
    )


def test_review_returns_updated_card_and_log():
    card = Card()
    original_due = card.due
    updated, log = review(card, correct=True, response_time_ms=1_000)
    assert updated.due is not None
    assert updated.due != original_due
    assert log.rating == Rating.Easy


def test_review_incorrect_logs_again():
    _, log = review(Card(), correct=False, response_time_ms=500)
    assert log.rating == Rating.Again


def _shortcut(action: str) -> Shortcut:
    return Shortcut(action=action, keys=("ctrl+x",))


def _pack(*actions: str) -> Pack:
    return Pack(
        id="t",
        name="t",
        description="t",
        shortcuts=tuple(_shortcut(a) for a in actions),
    )


def test_select_session_no_cards_returns_new_capped():
    pack = _pack("a", "b", "c", "d", "e", "f", "g")
    queue = select_session(pack, {}, new_per_session=3)
    assert [s.action for s in queue] == ["a", "b", "c"]


def test_select_session_due_cards_first_then_new():
    pack = _pack("a", "b", "c", "d")
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    cards = {
        pack.shortcut_id(pack.shortcuts[0]): Card(due=now - timedelta(hours=1)),  # due
        pack.shortcut_id(pack.shortcuts[1]): Card(
            due=now + timedelta(hours=1)
        ),  # not due
    }
    queue = select_session(pack, cards, new_per_session=1, now=now)
    # Due first (a), then 1 new (c, since b is not-due, d is the second new)
    assert [s.action for s in queue] == ["a", "c"]


def test_select_session_skips_not_due_cards():
    pack = _pack("a", "b")
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    future = Card(due=now + timedelta(days=7))
    cards = {pack.shortcut_id(s): future for s in pack.shortcuts}
    queue = select_session(pack, cards, now=now)
    assert queue == []


def test_select_session_card_with_no_due_treated_as_due():
    pack = _pack("a")
    cards = {
        pack.shortcut_id(pack.shortcuts[0]): Card()
    }  # default due=None? actually Card() sets due
    # Card() may set due to now; either way fresh card with no schedule = due
    queue = select_session(pack, cards)
    assert len(queue) == 1


def test_select_session_excludes_disabled():
    pack = _pack("a", "b", "c")
    disabled = {pack.shortcut_id(pack.shortcuts[1])}
    queue = select_session(pack, {}, disabled=disabled, new_per_session=10)
    assert [s.action for s in queue] == ["a", "c"]


def test_select_session_introduces_shared_unseen_shortcuts():
    """A shortcut shared with another pack, with FSRS state but not due, should
    be introduced once in this pack."""
    pack = Pack(
        id="python_repl",
        name="p",
        description="d",
        shortcuts=(
            Shortcut(
                action="Move to start of line",
                keys=("ctrl+a",),
                shared_id="readline:Move to start of line",
            ),
        ),
    )
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    cards = {pack.shortcut_id(pack.shortcuts[0]): Card(due=now + timedelta(days=5))}
    # Not seen yet in python_repl: include as intro.
    queue = select_session(pack, cards, now=now, seen=set())
    assert len(queue) == 1
    # After being seen here: skip (not due).
    seen = {f"python_repl::{pack.shortcut_id(pack.shortcuts[0])}"}
    queue = select_session(pack, cards, now=now, seen=seen)
    assert queue == []


def test_compute_personal_thresholds_returns_none_below_minimum():
    times = list(range(100, 100 * PERSONAL_MIN_REVIEWS, 100))
    assert len(times) == PERSONAL_MIN_REVIEWS - 1
    assert compute_personal_thresholds(times) is None


def test_compute_personal_thresholds_uses_percentiles():
    times = list(range(1000, 1000 + 100 * 100, 100))
    assert len(times) == 100
    result = compute_personal_thresholds(times)
    assert result is not None
    assert result.fast_ms < result.slow_ms
    assert result.fast_ms == sorted(times)[round(30 / 100 * 99)]
    assert result.slow_ms == sorted(times)[round(90 / 100 * 99)]


def test_compute_personal_thresholds_filters_insane_values():
    sane = [2000] * PERSONAL_MIN_REVIEWS
    insane = [200_000, -5, None]
    result = compute_personal_thresholds(sane + insane)
    assert result is not None
    assert result.fast_ms == 2000
    assert result.slow_ms == 2000


def test_compute_personal_thresholds_filters_none_values():
    times = [None] * 50
    assert compute_personal_thresholds(times) is None


def test_blend_thresholds_weight_zero_is_absolute():
    absolute = Thresholds(fast_ms=2000, slow_ms=8000)
    personal = Thresholds(fast_ms=1000, slow_ms=5000)
    result = blend_thresholds(absolute, personal, weight=0.0)
    assert result == absolute


def test_blend_thresholds_weight_one_is_personal():
    absolute = Thresholds(fast_ms=2000, slow_ms=8000)
    personal = Thresholds(fast_ms=1000, slow_ms=5000)
    result = blend_thresholds(absolute, personal, weight=1.0)
    assert result == personal


def test_blend_thresholds_midpoint():
    absolute = Thresholds(fast_ms=2000, slow_ms=8000)
    personal = Thresholds(fast_ms=1000, slow_ms=6000)
    result = blend_thresholds(absolute, personal, weight=0.5)
    assert result.fast_ms == 1500
    assert result.slow_ms == 7000


def test_blend_thresholds_clamps_weight():
    absolute = Thresholds(fast_ms=2000, slow_ms=8000)
    personal = Thresholds(fast_ms=1000, slow_ms=5000)
    assert blend_thresholds(absolute, personal, weight=-1.0) == absolute
    assert blend_thresholds(absolute, personal, weight=2.0) == personal


def test_get_thresholds_returns_defaults_below_minimum():
    signals = [{"response_time_ms": 1500}] * (PERSONAL_MIN_REVIEWS - 1)
    assert get_thresholds(signals) == DEFAULT_THRESHOLDS


def test_get_thresholds_uses_custom_defaults_below_minimum():
    custom = Thresholds(fast_ms=1_500, slow_ms=6_000)
    signals = [{"response_time_ms": 1500}] * (PERSONAL_MIN_REVIEWS - 1)
    assert get_thresholds(signals, defaults=custom) == custom


def test_get_thresholds_returns_personal_above_full():
    signals = [
        {"response_time_ms": i * 100} for i in range(1, PERSONAL_FULL_REVIEWS + 1)
    ]
    result = get_thresholds(signals)
    personal = compute_personal_thresholds([s["response_time_ms"] for s in signals])
    assert result == personal


def test_get_thresholds_blends_between_min_and_full():
    n = (PERSONAL_MIN_REVIEWS + PERSONAL_FULL_REVIEWS) // 2
    signals = [{"response_time_ms": i * 10} for i in range(1, n + 1)]
    result = get_thresholds(signals)
    personal = compute_personal_thresholds([s["response_time_ms"] for s in signals])
    assert personal is not None
    assert personal.fast_ms < result.fast_ms < DEFAULT_THRESHOLDS.fast_ms


def test_get_thresholds_ignores_missing_response_time():
    signals = [{}] * 50
    assert get_thresholds(signals) == DEFAULT_THRESHOLDS


# --- select_multi_session ---


def test_multi_session_single_pack_matches_select_session():
    pack = _pack("a", "b", "c")
    result = select_multi_session([pack], {}, new_per_session=2)
    actions = [s.action for s, p in result]
    assert actions == ["a", "b"]
    assert all(p is pack for _, p in result)


def test_multi_session_merges_due_from_multiple_packs():
    pack_a = Pack(id="a", name="a", description="a", shortcuts=(_shortcut("x"),))
    pack_b = Pack(id="b", name="b", description="b", shortcuts=(_shortcut("y"),))
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    cards = {
        "a:x": Card(due=now - timedelta(hours=1)),
        "b:y": Card(due=now - timedelta(hours=2)),
    }
    result = select_multi_session([pack_a, pack_b], cards, now=now)
    actions = [(s.action, p.id) for s, p in result]
    assert ("x", "a") in actions
    assert ("y", "b") in actions


def test_multi_session_caps_new_across_packs():
    pack_a = _pack("a1", "a2", "a3")
    pack_b = Pack(
        id="b",
        name="b",
        description="b",
        shortcuts=(
            _shortcut("b1"),
            _shortcut("b2"),
            _shortcut("b3"),
        ),
    )
    result = select_multi_session([pack_a, pack_b], {}, new_per_session=4)
    assert len(result) == 4
    actions = [s.action for s, _ in result]
    assert actions == ["a1", "a2", "a3", "b1"]


def test_multi_session_deduplicates_shared_shortcuts():
    shared = Shortcut(
        action="Move to start of line",
        keys=("ctrl+a",),
        shared_id="readline:Move to start of line",
    )
    pack_a = Pack(id="readline", name="r", description="r", shortcuts=(shared,))
    pack_b = Pack(id="python_repl", name="p", description="p", shortcuts=(shared,))
    result = select_multi_session([pack_a, pack_b], {}, new_per_session=10)
    assert len(result) == 1
    assert result[0][1].id == "readline"


def test_multi_session_deduplicates_due_shared_shortcuts():
    shared = Shortcut(
        action="Move to start of line",
        keys=("ctrl+a",),
        shared_id="readline:Move to start of line",
    )
    pack_a = Pack(id="readline", name="r", description="r", shortcuts=(shared,))
    pack_b = Pack(id="python_repl", name="p", description="p", shortcuts=(shared,))
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    cards = {"readline:Move to start of line": Card(due=now - timedelta(hours=1))}
    result = select_multi_session([pack_a, pack_b], cards, now=now)
    assert len(result) == 1
    assert result[0][1].id == "readline"


def test_multi_session_excludes_disabled():
    pack_a = _pack("a", "b")
    pack_b = Pack(id="b", name="b", description="b", shortcuts=(_shortcut("c"),))
    disabled = {"t:b"}
    result = select_multi_session(
        [pack_a, pack_b],
        {},
        disabled=disabled,
        new_per_session=10,
    )
    actions = [s.action for s, _ in result]
    assert "b" not in actions
    assert "a" in actions
    assert "c" in actions


def test_multi_session_empty_packs():
    result = select_multi_session([], {})
    assert result == []


# --- apply_assessment ---


def test_apply_assessment_disables_correct():
    results = [("a:Move", True), ("a:Delete", False)]
    disabled = apply_assessment(results, set())
    assert "a:Move" in disabled
    assert "a:Delete" not in disabled


def test_apply_assessment_enables_previously_disabled_wrong():
    results = [("a:Move", False)]
    disabled = apply_assessment(results, {"a:Move"})
    assert "a:Move" not in disabled


def test_apply_assessment_preserves_unrelated_disabled():
    results = [("a:Move", True)]
    disabled = apply_assessment(results, {"other:thing"})
    assert "other:thing" in disabled
    assert "a:Move" in disabled


def test_reject_from_assessment():
    disabled = {"a:Move"}
    result = reject_from_assessment(disabled, {"b:Delete", "c:Paste"})
    assert result == {"a:Move", "b:Delete", "c:Paste"}
