import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Shortcut:
    action: str
    keys: tuple[str, ...]
    tags: tuple[str, ...] = ()
    hint: str | None = None
    capturable: bool = True


@dataclass(frozen=True)
class Pack:
    id: str
    name: str
    description: str
    shortcuts: tuple[Shortcut, ...]

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
            capturable=item.get("capturable", True),
        )
        for item in data.get("shortcuts", [])
    )
    return Pack(
        id=pack_meta["id"],
        name=pack_meta["name"],
        description=pack_meta["description"],
        shortcuts=shortcuts,
    )


def load_pack(path: Path) -> Pack:
    with path.open("rb") as f:
        return parse_pack(tomllib.load(f))
