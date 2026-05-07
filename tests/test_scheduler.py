from fsrs import Card, Rating

from keypal.scheduler import FAST_MS, SLOW_MS, classify, review


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
