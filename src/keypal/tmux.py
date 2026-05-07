import os
import re
import subprocess
from dataclasses import replace

from keypal.keys import keys_by_simplicity
from keypal.models import Pack


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


_BIND_RE = re.compile(r"^bind-key\s+(?:-\S+\s+)*-T\s+prefix\s+(\S+)\s+(.+)$")


def canonical_tmux_command(cmd: str) -> str:
    """Strip trailing numeric arguments so 'resize-pane -L 2' matches 'resize-pane -L'."""
    parts = cmd.strip().split()
    while parts and parts[-1].isdigit():
        parts.pop()
    return " ".join(parts)


def parse_tmux_bindings(output: str | None = None) -> dict[str, list[str]]:
    """Map canonical tmux command -> list of tmux key tokens (e.g. 'C-a', 'h')."""
    if output is None:
        if not inside_tmux():
            return {}
        try:
            result = subprocess.run(
                ["tmux", "list-keys", "-T", "prefix"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except Exception:
            return {}
        if result.returncode != 0:
            return {}
        output = result.stdout

    bindings: dict[str, list[str]] = {}
    for line in output.splitlines():
        m = _BIND_RE.match(line.strip())
        if not m:
            continue
        key, command = m.group(1), m.group(2).strip()
        canonical = canonical_tmux_command(command)
        if not canonical:
            continue
        bindings.setdefault(canonical, []).append(key)
    return bindings


def apply_tmux_overrides(pack: Pack, *, bindings: dict[str, list[str]] | None = None) -> Pack:
    """Substitute keys/prefix from the user's live tmux config for matching commands."""
    if pack.id != "tmux":
        return pack
    if bindings is None:
        bindings = parse_tmux_bindings()
    if not bindings:
        return pack

    new_shortcuts = []
    for shortcut in pack.shortcuts:
        if shortcut.command and shortcut.command in bindings:
            converted = [tmux_to_keypal_combo(k) for k in bindings[shortcut.command]]
            new_keys = tuple(keys_by_simplicity(converted))
            new_shortcuts.append(replace(shortcut, keys=new_keys))
        else:
            new_shortcuts.append(shortcut)

    new_prefix = current_tmux_prefix() or pack.prefix
    return replace(pack, shortcuts=tuple(new_shortcuts), prefix=new_prefix)
