from collections.abc import Iterable, Mapping

MODIFIERS = frozenset({"ctrl", "alt", "shift", "meta", "super"})

# Textual reports symbol keys by name (e.g. event.key="comma" when "," is pressed).
# Pack TOMLs typically use the character ("ctrl+,"). Canonicalize names → characters
# so both forms compare equal.
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
    "\n": "enter",  # raw newline byte; Textual sometimes reports this for Enter or Alt+Enter
    "\r": "enter",  # raw carriage return byte; same situation
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


_PLUS_KEY_SENTINEL = "\x00plus\x00"


def normalize(combo: str) -> str:
    s = combo.strip().lower()
    # "+" is both the separator and a valid key. Detect plus-as-key cases
    # ("+", "ctrl++", etc.) by substituting a sentinel before splitting.
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
    """Split a normalized combo into tokens, treating '+' as a key when needed."""
    if normalized == "+":
        return ["+"]
    if normalized.endswith("++"):
        return [p for p in normalized[:-1].split("+") if p] + ["+"]
    return normalized.split("+")


# Terminals encode several Ctrl combos as the same byte as a named key.
# These are physically indistinguishable to any TUI: pressing Ctrl+H sends
# 0x08 (Backspace), Ctrl+I sends 0x09 (Tab), Ctrl+M sends 0x0D (Enter),
# Ctrl+[ sends 0x1B (Escape).
TERMINAL_EQUIVALENTS: tuple[frozenset[str], ...] = (
    frozenset({"ctrl+h", "backspace"}),
    frozenset({"ctrl+i", "tab"}),
    frozenset({"ctrl+m", "enter"}),
    frozenset({"ctrl+[", "escape"}),
)


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
    for group in TERMINAL_EQUIVALENTS:
        if normalized_pressed in group and group & expected_set:
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


def split_combo(combo: str) -> tuple[list[str], str]:
    """Split a combo into (sorted modifiers, base key)."""
    parts = _split_normalized(normalize(combo))
    mods = sorted(p for p in parts if p in MODIFIERS)
    base = [p for p in parts if p not in MODIFIERS]
    return mods, base[0]


def extract_parts(key_event: str) -> tuple[set[str], str | None]:
    """Extract the modifier set and base key from a raw keypress."""
    try:
        parts = _split_normalized(normalize(key_event))
    except ValueError:
        return set(), None
    mods = {p for p in parts if p in MODIFIERS}
    base = [p for p in parts if p not in MODIFIERS]
    return mods, base[0] if base else None


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
    """Sort keys so simpler ones come first: fewer modifiers, then shorter."""

    def rank(k: str) -> tuple[int, int]:
        try:
            parts = _split_normalized(normalize(k))
        except ValueError:
            return (10, len(k))
        modifier_count = sum(1 for p in parts if p in MODIFIERS)
        return (modifier_count, len(k))

    return sorted(keys, key=rank)
