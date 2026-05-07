import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Shortcut:
    action: str
    keys: tuple[str, ...]
    tags: tuple[str, ...] = ()
    hint: str | None = None
    command: str | None = None  # stable ID joining shortcut to live config (e.g. tmux command, obsidian command id)


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    description: str
    shortcuts: tuple[Shortcut, ...]
    prefix: str | None = None

    def shortcut_id(self, shortcut: Shortcut) -> str:
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
    with path.open("rb") as f:
        return parse_pack(tomllib.load(f))


def builtin_packs() -> tuple[Pack, ...]:
    # Imported lazily to avoid a circular dependency: providers import Pack from this module.
    from keypal.obsidian import apply_obsidian_overrides
    from keypal.tmux import apply_tmux_overrides

    package = resources.files("keypal.packs")
    packs = []
    for entry in package.iterdir():
        if entry.name.endswith(".toml"):
            with entry.open("rb") as f:
                pack = parse_pack(tomllib.load(f))
            pack = apply_tmux_overrides(pack)
            pack = apply_obsidian_overrides(pack)
            packs.append(pack)
    return tuple(packs)
