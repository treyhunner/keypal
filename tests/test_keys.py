import pytest

from keypal.keys import matches, normalize


def test_normalize_lowercases():
    assert normalize("Ctrl+A") == "ctrl+a"


def test_normalize_sorts_modifiers():
    assert normalize("Shift+Ctrl+Left") == "ctrl+shift+left"
    assert normalize("Alt+Ctrl+f") == "alt+ctrl+f"


def test_normalize_idempotent():
    assert normalize(normalize("Shift+Ctrl+Left")) == normalize("Shift+Ctrl+Left")


def test_normalize_no_modifier():
    assert normalize("escape") == "escape"
    assert normalize("F10") == "f10"


def test_normalize_strips_whitespace():
    assert normalize("  ctrl + a  ") == "ctrl+a"


def test_normalize_rejects_empty_token():
    with pytest.raises(ValueError):
        normalize("ctrl++a")


def test_normalize_rejects_no_main_key():
    with pytest.raises(ValueError):
        normalize("ctrl+shift")


def test_normalize_rejects_multiple_main_keys():
    with pytest.raises(ValueError):
        normalize("a+b")


def test_matches_single_expected():
    assert matches("Ctrl+A", ["ctrl+a"])
    assert not matches("Ctrl+A", ["ctrl+b"])


def test_matches_multiple_expected():
    assert matches("alt+backspace", ["ctrl+w", "alt+backspace"])
    assert not matches("ctrl+a", ["ctrl+w", "alt+backspace"])


def test_matches_normalizes_both_sides():
    assert matches("SHIFT+CTRL+LEFT", ["ctrl+shift+left"])
