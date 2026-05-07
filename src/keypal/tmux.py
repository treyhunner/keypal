import os
import subprocess


def inside_tmux() -> bool:
    return bool(os.environ.get("TMUX"))


def tmux_to_keypal_combo(tmux_combo: str) -> str:
    """Convert tmux's notation (e.g. 'C-a', 'M-x', 'S-Tab') to keypal's form ('ctrl+a')."""
    if not tmux_combo:
        return ""
    parts: list[str] = []
    rest = tmux_combo
    while len(rest) >= 2 and rest[0] in "CMS" and rest[1] == "-":
        match rest[0]:
            case "C":
                parts.append("ctrl")
            case "M":
                parts.append("alt")
            case "S":
                parts.append("shift")
        rest = rest[2:]
    parts.append(rest.lower())
    return "+".join(parts)


def _show_option(name: str) -> str:
    try:
        result = subprocess.run(
            ["tmux", "show-option", "-gv", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _set_option(name: str, value: str) -> None:
    try:
        subprocess.run(
            ["tmux", "set-option", "-g", name, value],
            capture_output=True,
            check=False,
            timeout=2,
        )
    except Exception:
        pass


def current_tmux_prefix() -> str | None:
    """Return the tmux prefix in keypal's combo form, or None if not in tmux / not detectable."""
    if not inside_tmux():
        return None
    raw = _show_option("prefix")
    if not raw:
        return None
    return tmux_to_keypal_combo(raw)


class TmuxPrefixSwap:
    """Temporarily replace tmux's prefix while a chord pack is being practiced.

    Saves the original `prefix` and `prefix2` server options, sets both to `None`
    (which tmux interprets as "no prefix"), and restores on deactivate.
    """

    def __init__(self) -> None:
        self._original_prefix: str | None = None
        self._original_prefix2: str | None = None
        self._activated = False

    def activate(self) -> bool:
        if not inside_tmux():
            return False
        self._original_prefix = _show_option("prefix") or "C-b"
        self._original_prefix2 = _show_option("prefix2") or "None"
        _set_option("prefix", "None")
        _set_option("prefix2", "None")
        self._activated = True
        return True

    def deactivate(self) -> None:
        if not self._activated:
            return
        if self._original_prefix:
            _set_option("prefix", self._original_prefix)
        if self._original_prefix2:
            _set_option("prefix2", self._original_prefix2)
        self._activated = False

    @property
    def active(self) -> bool:
        return self._activated
