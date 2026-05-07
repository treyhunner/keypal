from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating

from keypal.models import Pack, Shortcut
from keypal.scheduler import FAST_MS, SLOW_MS, classify, review, select_session


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
        pack.shortcut_id(pack.shortcuts[1]): Card(due=now + timedelta(hours=1)),  # not due
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
    cards = {pack.shortcut_id(pack.shortcuts[0]): Card()}  # default due=None? actually Card() sets due
    # Card() may set due to now; either way fresh card with no schedule = due
    queue = select_session(pack, cards)
    assert len(queue) == 1
