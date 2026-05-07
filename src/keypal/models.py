from dataclasses import dataclass


@dataclass(frozen=True)
class Shortcut:
    action: str
    keys: tuple[str, ...]
    tags: tuple[str, ...] = ()
    hint: str | None = None
    capturable: bool = True


@dataclass(frozen=True)
class Pack:
    filename: str
    name: str
    description: str
    shortcuts: tuple[Shortcut, ...]

    def shortcut_id(self, shortcut: Shortcut) -> str:
        return f"{self.filename}:{shortcut.action}"
