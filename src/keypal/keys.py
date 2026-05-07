from collections.abc import Iterable

MODIFIERS = frozenset({"ctrl", "alt", "shift", "meta", "super"})

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


def normalize(combo: str) -> str:
    parts = [part.strip().lower() for part in combo.strip().split("+")]
    if "" in parts:
        raise ValueError(f"Empty token in key combo {combo!r}")
    modifiers = sorted(p for p in parts if p in MODIFIERS)
    keys = [p for p in parts if p not in MODIFIERS]
    if len(keys) != 1:
        raise ValueError(f"Expected exactly one non-modifier key in {combo!r}, got {keys}")
    return "+".join([*modifiers, keys[0]])


def matches(pressed: str, expected: Iterable[str]) -> bool:
    try:
        normalized = normalize(pressed)
    except ValueError:
        return False
    return normalized in {normalize(e) for e in expected}


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
    return [prettify_key(part) for part in normalize(combo).split("+")]
