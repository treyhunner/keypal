from collections.abc import Iterable

MODIFIERS = frozenset({"ctrl", "alt", "shift", "meta", "super"})


def normalize(combo: str) -> str:
    parts = [part.strip().lower() for part in combo.strip().split("+")]
    if "" in parts:
        raise ValueError(f"Empty token in key combo {combo!r}")
    modifiers = sorted(p for p in parts if p in MODIFIERS)
    keys = [p for p in parts if p not in MODIFIERS]
    if len(keys) != 1:
        raise ValueError(f"Expected exactly one non-modifier key in {combo!r}, got {keys}")
    return "+".join([*modifiers, keys[0]])


def matches(pressed: str, expected: Iterable[str]) -> bool:
    return normalize(pressed) in {normalize(e) for e in expected}
