import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs
from fsrs import Card, ReviewLog


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

    def append_review(self, shortcut_id: str, log: ReviewLog) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        record = {"shortcut_id": shortcut_id, "log": log.to_dict()}
        with open(self.review_log_path, mode="at") as file:
            file.write(json.dumps(record) + "\n")

    def read_reviews(self) -> Iterator[tuple[str, ReviewLog]]:
        if not self.review_log_path.exists():
            return
        with open(self.review_log_path) as file:
            for line in file:
                if not line.strip():
                    continue
                record = json.loads(line)
                yield record["shortcut_id"], ReviewLog.from_dict(record["log"])

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
