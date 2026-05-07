import json
import os
from dataclasses import replace
from pathlib import Path

from keypal.keys import keys_by_simplicity
from keypal.models import Pack


_MODIFIER_MAP = {
    "Mod": "ctrl",  # Ctrl on Linux/Windows, Cmd on macOS — keypal sees Ctrl on Linux
    "Ctrl": "ctrl",
    "Alt": "alt",
    "Shift": "shift",
    "Meta": "meta",
}

_KEY_MAP = {
    "ArrowLeft": "left",
    "ArrowRight": "right",
    "ArrowUp": "up",
    "ArrowDown": "down",
    "Enter": "enter",
    "Escape": "escape",
    "Tab": "tab",
    "Space": "space",
    "Backspace": "backspace",
    "Delete": "delete",
    "Home": "home",
    "End": "end",
    "PageUp": "page_up",
    "PageDown": "page_down",
}


def obsidian_binding_to_combo(binding: dict) -> str:
    parts = [_MODIFIER_MAP.get(m, m.lower()) for m in binding.get("modifiers", [])]
    key = binding.get("key", "")
    parts.append(_KEY_MAP.get(key, key.lower() if key else ""))
    return "+".join(p for p in parts if p)


def find_obsidian_hotkeys() -> Path | None:
    """Locate the user's hotkeys.json by env var or by reading Obsidian's vault list."""
    if path := os.environ.get("KEYPAL_OBSIDIAN_HOTKEYS"):
        p = Path(path).expanduser()
        return p if p.exists() else None

    # Linux: Obsidian stores its main config (with vault list) here.
    config_path = Path.home() / ".config" / "obsidian" / "obsidian.json"
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text())
    except Exception:
        return None
    for vault_info in data.get("vaults", {}).values():
        vault_path = Path(vault_info.get("path", "")).expanduser()
        hotkeys = vault_path / ".obsidian" / "hotkeys.json"
        if hotkeys.exists():
            return hotkeys
    return None


def parse_obsidian_hotkeys(path: Path) -> dict[str, list[str]]:
    """Parse a hotkeys.json file into command_id -> list of keypal combos."""
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    result: dict[str, list[str]] = {}
    for command_id, bindings in data.items():
        if not isinstance(bindings, list) or not bindings:
            continue
        keys = [obsidian_binding_to_combo(b) for b in bindings if isinstance(b, dict)]
        keys = [k for k in keys if k]
        if keys:
            result[command_id] = keys
    return result


def apply_obsidian_overrides(pack: Pack, *, hotkeys: dict[str, list[str]] | None = None) -> Pack:
    """Substitute keys from the user's hotkeys.json on shortcuts whose command matches."""
    if pack.id != "obsidian":
        return pack
    if hotkeys is None:
        path = find_obsidian_hotkeys()
        if not path:
            return pack
        hotkeys = parse_obsidian_hotkeys(path)
    if not hotkeys:
        return pack

    new_shortcuts = []
    for shortcut in pack.shortcuts:
        if shortcut.command and shortcut.command in hotkeys:
            new_keys = tuple(keys_by_simplicity(hotkeys[shortcut.command]))
            new_shortcuts.append(replace(shortcut, keys=new_keys))
        else:
            new_shortcuts.append(shortcut)
    return replace(pack, shortcuts=tuple(new_shortcuts))
