import tomllib
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Shortcut:
    action: str
    keys: tuple[str, ...]
    tags: tuple[str, ...] = ()
    hint: str | None = None
    command: str | None = (
        None  # stable ID joining shortcut to live config (e.g. tmux command, obsidian command id)
    )
    shared_id: str | None = (
        None  # when set, identifies the FSRS card across packs (e.g. "readline:Move to start of line")
    )
    demo_before: str | None = (
        None  # text-edit demo: state before the shortcut runs (use '│' as cursor)
    )
    demo_after: str | None = None  # text-edit demo: state after the shortcut runs


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    description: str
    shortcuts: tuple[Shortcut, ...]
    prefix: str | None = None

    def shortcut_id(self, shortcut: Shortcut) -> str:
        if shortcut.shared_id:
            return shortcut.shared_id
        return f"{self.id}:{shortcut.action}"


def parse_pack(data: dict[str, Any]) -> Pack:
    pack_meta = data["pack"]
    shortcuts = tuple(
        Shortcut(
            action=item["action"],
            keys=tuple(item["keys"]),
            tags=tuple(item.get("tags", ())),
            hint=item.get("hint"),
            command=item.get("command"),
            shared_id=item.get("shared_id"),
            demo_before=item.get("demo_before"),
            demo_after=item.get("demo_after"),
        )
        for item in data.get("shortcuts", [])
    )
    return Pack(
        id=pack_meta["id"],
        name=pack_meta["name"],
        description=pack_meta["description"],
        shortcuts=shortcuts,
        prefix=pack_meta.get("prefix"),
    )


def load_pack(path: Path) -> Pack:
    return parse_pack(tomllib.loads(path.read_text()))


def builtin_packs() -> tuple[Pack, ...]:
    # Imported lazily to avoid a circular dependency: providers import Pack from this module.
    from keypal.obsidian import apply_obsidian_overrides
    from keypal.tmux import apply_tmux_overrides

    package = resources.files("keypal.packs")
    packs: list[Pack] = []
    for entry in package.iterdir():
        if entry.name.endswith(".toml"):
            pack = parse_pack(tomllib.loads(entry.read_text()))
            pack = apply_tmux_overrides(pack)
            pack = apply_obsidian_overrides(pack)
            packs.append(pack)
    return _inherit_demos(packs)


def _inherit_demos(packs: list[Pack]) -> tuple[Pack, ...]:
    """Fill in missing demo fields on shared shortcuts from their shared_id source."""
    demo_by_id: dict[str, tuple[str, str]] = {}
    for pack in packs:
        for shortcut in pack.shortcuts:
            if shortcut.demo_before and shortcut.demo_after:
                demo_by_id[pack.shortcut_id(shortcut)] = (
                    shortcut.demo_before,
                    shortcut.demo_after,
                )
    result = []
    for pack in packs:
        new_shortcuts = []
        for shortcut in pack.shortcuts:
            if (
                shortcut.shared_id
                and not shortcut.demo_before
                and shortcut.shared_id in demo_by_id
            ):
                before, after = demo_by_id[shortcut.shared_id]
                new_shortcuts.append(
                    replace(shortcut, demo_before=before, demo_after=after)
                )
            else:
                new_shortcuts.append(shortcut)
        result.append(replace(pack, shortcuts=tuple(new_shortcuts)))
    return tuple(result)
