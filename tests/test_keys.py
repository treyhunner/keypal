import pytest

from keypal.keys import matches, normalize, prettify_combo, prettify_key


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


def test_matches_returns_false_on_unparseable_pressed():
    # Unparseable input should not raise; just doesn't match.
    assert matches("ctrl++", ["ctrl+a"]) is False
    assert matches("ctrl+shift", ["ctrl+a"]) is False


def test_matches_accepts_alias():
    aliases = {"alt+f": ["ctrl+right"]}
    assert matches("ctrl+right", ["alt+f"], aliases) is True
    assert matches("ctrl+right", ["alt+b"], aliases) is False


def test_matches_alias_normalizes_both_sides():
    aliases = {"alt+f": ["Ctrl+Right"]}
    assert matches("CTRL+RIGHT", ["Alt+F"], aliases) is True


def test_matches_without_alias_still_works():
    assert matches("ctrl+a", ["ctrl+a"], {}) is True


def test_prettify_key_modifiers():
    assert prettify_key("ctrl") == "Ctrl"
    assert prettify_key("Alt") == "Alt"
    assert prettify_key("shift") == "Shift"


def test_prettify_key_letters():
    assert prettify_key("a") == "A"
    assert prettify_key("Z") == "Z"


def test_prettify_key_function_keys():
    assert prettify_key("f1") == "F1"
    assert prettify_key("F10") == "F10"


def test_prettify_key_special():
    assert prettify_key("space") == "Space"
    assert prettify_key("escape") == "Esc"
    assert prettify_key("left") == "←"
    assert prettify_key("page_up") == "Page Up"


def test_prettify_key_unknown_falls_back():
    assert prettify_key("nonsense") == "Nonsense"
    assert prettify_key("foo_bar") == "Foo Bar"


def test_prettify_combo():
    assert prettify_combo("ctrl+a") == ["Ctrl", "A"]
    assert prettify_combo("Shift+Ctrl+Left") == ["Ctrl", "Shift", "←"]
    assert prettify_combo("alt+backspace") == ["Alt", "Backspace"]
