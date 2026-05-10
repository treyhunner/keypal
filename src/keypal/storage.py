import json
import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

import platformdirs
from fsrs import Card, ReviewLog


@dataclass
class Settings:
    new_per_session: int = 5
    fast_ms: int = 2_000
    slow_ms: int = 8_000
    auto_advance_secs: float = 4.0


def default_data_dir() -> Path:
    if override := os.environ.get("KEYPAL_DATA_DIR"):
        return Path(override)
    return Path(platformdirs.user_data_dir("keypal"))


@dataclass
class Storage:
    base_dir: Path = field(default_factory=default_data_dir)

    @property
    def cards_path(self) -> Path:
        return self.base_dir / "cards.json"

    @property
    def review_log_path(self) -> Path:
        return self.base_dir / "review_log.jsonl"

    @property
    def aliases_path(self) -> Path:
        return self.base_dir / "aliases.json"

    @property
    def disabled_path(self) -> Path:
        return self.base_dir / "disabled.json"

    @property
    def seen_path(self) -> Path:
        return self.base_dir / "seen.json"

    def load_cards(self) -> dict[str, Card]:
        if not self.cards_path.exists():
            return {}
        raw = json.loads(self.cards_path.read_text())
        return {sid: Card.from_dict(data) for sid, data in raw.items()}

    def save_cards(self, cards: dict[str, Card]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        serialized = {sid: card.to_dict() for sid, card in cards.items()}
        self.cards_path.write_text(json.dumps(serialized, indent=2) + "\n")

    def append_review(
        self,
        shortcut_id: str,
        log: ReviewLog,
        signals: dict[str, int | None] | None = None,
    ) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        record: dict = {"shortcut_id": shortcut_id, "log": log.to_dict()}
        if signals:
            record["signals"] = signals
        with open(self.review_log_path, mode="at") as file:
            file.write(json.dumps(record) + "\n")

    def read_reviews(self) -> Iterator[tuple[str, ReviewLog, dict]]:
        if not self.review_log_path.exists():
            return
        with open(self.review_log_path) as file:
            for line in file:
                if not line.strip():
                    continue
                record = json.loads(line)
                signals = record.get("signals", {})
                yield record["shortcut_id"], ReviewLog.from_dict(record["log"]), signals

    def load_aliases(self) -> dict[str, set[str]]:
        if not self.aliases_path.exists():
            return {}
        raw = json.loads(self.aliases_path.read_text())
        return {expected: set(pressed) for expected, pressed in raw.items()}

    def save_aliases(self, aliases: dict[str, set[str]]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        serialized = {
            expected: sorted(pressed) for expected, pressed in aliases.items()
        }
        self.aliases_path.write_text(json.dumps(serialized, indent=2) + "\n")

    def load_disabled(self) -> set[str]:
        if not self.disabled_path.exists():
            return set()
        return set(json.loads(self.disabled_path.read_text()))

    def save_disabled(self, disabled: set[str]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.disabled_path.write_text(json.dumps(sorted(disabled), indent=2) + "\n")

    def load_seen(self) -> set[str]:
        """Set of "{pack_id}::{shortcut_id}" pairs the user has reviewed in that specific pack."""
        if not self.seen_path.exists():
            return set()
        return set(json.loads(self.seen_path.read_text()))

    def save_seen(self, seen: set[str]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.seen_path.write_text(json.dumps(sorted(seen), indent=2) + "\n")

    @property
    def selected_packs_path(self) -> Path:
        return self.base_dir / "selected_packs.json"

    def load_selected_packs(self) -> set[str] | None:
        if not self.selected_packs_path.exists():
            return None
        return set(json.loads(self.selected_packs_path.read_text()))

    def save_selected_packs(self, pack_ids: set[str]) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.selected_packs_path.write_text(
            json.dumps(sorted(pack_ids), indent=2) + "\n"
        )

    @property
    def settings_path(self) -> Path:
        return self.base_dir / "settings.json"

    def load_settings(self) -> Settings:
        if not self.settings_path.exists():
            return Settings()
        raw = json.loads(self.settings_path.read_text())
        kwargs = {}
        for key in ("new_per_session", "fast_ms", "slow_ms", "auto_advance_secs"):
            if key in raw:
                kwargs[key] = raw[key]
        return Settings(**kwargs)

    def save_settings(self, settings: Settings) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(json.dumps(asdict(settings), indent=2) + "\n")
