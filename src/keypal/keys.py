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


def normalize(combo: str) -> str:
    parts = [part.strip().lower() for part in combo.strip().split("+")]
    if "" in parts:
        raise ValueError(f"Empty token in key combo {combo!r}")
    modifiers = sorted(p for p in parts if p in MODIFIERS)
    keys = [SYMBOL_NAMES.get(p, p) for p in parts if p not in MODIFIERS]
    if len(keys) != 1:
        raise ValueError(f"Expected exactly one non-modifier key in {combo!r}, got {keys}")
    return "+".join([*modifiers, keys[0]])


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
