from collections.abc import Iterable, Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

MODIFIERS = frozenset({"ctrl", "alt", "shift", "meta", "super"})

# Kept for backward compatibility: normalize() uses this to resolve names stored
# in aliases.json from the Textual era (e.g. "comma" -> ",").
SYMBOL_NAMES: dict[str, str] = {
    "comma": ",",
    "period": ".",
    "full_stop": ".",
    "semicolon": ";",
    "colon": ":",
    "exclamation_mark": "!",
    "question_mark": "?",
    "minus": "-",
    "hyphen": "-",
    "plus": "+",
    "equals": "=",
    "equals_sign": "=",
    "asterisk": "*",
    "slash": "/",
    "backslash": "\\",
    "underscore": "_",
    "tilde": "~",
    "grave_accent": "`",
    "caret": "^",
    "ampersand": "&",
    "at": "@",
    "hash": "#",
    "number_sign": "#",
    "dollar": "$",
    "dollar_sign": "$",
    "percent": "%",
    "percent_sign": "%",
    "left_parenthesis": "(",
    "right_parenthesis": ")",
    "left_bracket": "[",
    "right_bracket": "]",
    "left_brace": "{",
    "right_brace": "}",
    "left_curly_bracket": "{",
    "right_curly_bracket": "}",
    "less_than_sign": "<",
    "greater_than_sign": ">",
    "less_than": "<",
    "greater_than": ">",
    "quotation_mark": '"',
    "apostrophe": "'",
    "vertical_line": "|",
    "vertical_bar": "|",
    "bracketleft": "[",
    "bracketright": "]",
    "braceleft": "{",
    "braceright": "}",
    "bar": "|",
    "quoteleft": "`",
    "quotedbl": '"',
    "asciitilde": "~",
    "\n": "enter",
    "\r": "enter",
}

SPECIAL_KEY_NAMES: dict[str, str] = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "meta": "Meta",
    "super": "Super",
    "space": "Space",
    "enter": "Enter",
    "tab": "Tab",
    "escape": "Esc",
    "backspace": "Backspace",
    "delete": "Del",
    "left": "←",
    "right": "→",
    "up": "↑",
    "down": "↓",
    "page_up": "Page Up",
    "page_down": "Page Down",
    "home": "Home",
    "end": "End",
    "insert": "Ins",
}

QT_KEY_NAMES: dict[int, str] = {
    Qt.Key.Key_Space: "space",
    Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Escape: "escape",
    Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Left: "left",
    Qt.Key.Key_Right: "right",
    Qt.Key.Key_Up: "up",
    Qt.Key.Key_Down: "down",
    Qt.Key.Key_Home: "home",
    Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "page_up",
    Qt.Key.Key_PageDown: "page_down",
    Qt.Key.Key_Insert: "insert",
    Qt.Key.Key_F1: "f1",
    Qt.Key.Key_F2: "f2",
    Qt.Key.Key_F3: "f3",
    Qt.Key.Key_F4: "f4",
    Qt.Key.Key_F5: "f5",
    Qt.Key.Key_F6: "f6",
    Qt.Key.Key_F7: "f7",
    Qt.Key.Key_F8: "f8",
    Qt.Key.Key_F9: "f9",
    Qt.Key.Key_F10: "f10",
    Qt.Key.Key_F11: "f11",
    Qt.Key.Key_F12: "f12",
}

_PURE_MODIFIERS = frozenset(
    {
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
        Qt.Key.Key_CapsLock,
        Qt.Key.Key_NumLock,
        Qt.Key.Key_ScrollLock,
    }
)


def qt_event_to_combo(event: QKeyEvent) -> str | None:
    key = event.key()
    if key in _PURE_MODIFIERS:
        return None

    modifiers = event.modifiers()
    parts: list[str] = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("super")

    if key in QT_KEY_NAMES:
        key_name = QT_KEY_NAMES[key]
    else:
        text = event.text()
        if text and text.isprintable():
            char = text.lower()
            if "shift" in parts and len(char) == 1 and not char.isalpha():
                parts.remove("shift")
            key_name = char
        else:
            enum_name = Qt.Key(key).name
            if isinstance(enum_name, bytes):
                enum_name = enum_name.decode()
            key_name = enum_name.removeprefix("Key_").lower()

    parts.append(key_name)
    return "+".join(parts)


_PLUS_KEY_SENTINEL = "\x00plus\x00"


def normalize(combo: str) -> str:
    s = combo.strip().lower()
    if s == "+":
        s = _PLUS_KEY_SENTINEL
    elif s.endswith("++"):
        s = s[:-1] + _PLUS_KEY_SENTINEL
    parts = [part.strip() for part in s.split("+")]
    if "" in parts:
        raise ValueError(f"Empty token in key combo {combo!r}")
    parts = ["+" if p == _PLUS_KEY_SENTINEL else p for p in parts]
    modifiers = sorted(p for p in parts if p in MODIFIERS)
    keys = [SYMBOL_NAMES.get(p, p) for p in parts if p not in MODIFIERS]
    if len(keys) != 1:
        raise ValueError(
            f"Expected exactly one non-modifier key in {combo!r}, got {keys}"
        )
    return "+".join([*modifiers, keys[0]])


def _split_normalized(normalized: str) -> list[str]:
    if normalized == "+":
        return ["+"]
    if normalized.endswith("++"):
        return [p for p in normalized[:-1].split("+") if p] + ["+"]
    return normalized.split("+")


def matches(
    pressed: str,
    expected: Iterable[str],
    aliases: Mapping[str, Iterable[str]] | None = None,
) -> bool:
    try:
        normalized_pressed = normalize(pressed)
    except ValueError:
        return False
    expected_set = {normalize(e) for e in expected}
    if normalized_pressed in expected_set:
        return True
    if aliases:
        for exp in expected_set:
            for alias in aliases.get(exp, []):
                try:
                    if normalize(alias) == normalized_pressed:
                        return True
                except ValueError:
                    continue
    return False


def prettify_key(token: str) -> str:
    token = token.strip().lower()
    if token in SPECIAL_KEY_NAMES:
        return SPECIAL_KEY_NAMES[token]
    if token.startswith("f") and token[1:].isdigit():
        return token.upper()
    if len(token) == 1:
        return token.upper()
    return token.replace("_", " ").title()


def prettify_combo(combo: str) -> list[str]:
    return [prettify_key(part) for part in _split_normalized(normalize(combo))]


def keys_by_simplicity(keys: Iterable[str]) -> list[str]:
    def rank(k: str) -> tuple[int, int]:
        try:
            parts = _split_normalized(normalize(k))
        except ValueError:
            return (10, len(k))
        modifier_count = sum(1 for p in parts if p in MODIFIERS)
        return (modifier_count, len(k))

    return sorted(keys, key=rank)
