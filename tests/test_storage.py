from fsrs import Card, Rating, Scheduler

from keypal.storage import Storage, default_data_dir


def test_default_data_dir_uses_keypal_override(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYPAL_DATA_DIR", str(tmp_path))
    assert default_data_dir() == tmp_path


def test_default_data_dir_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("KEYPAL_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_data_dir() == tmp_path / "keypal"


def test_default_data_dir_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("KEYPAL_DATA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert default_data_dir().parts[-3:] == (".local", "share", "keypal")


def test_load_cards_returns_empty_when_missing(tmp_path):
    storage = Storage(base_dir=tmp_path)
    assert storage.load_cards() == {}


def test_save_and_load_cards_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    cards = {"readline:Move forward one word": Card()}
    storage.save_cards(cards)
    loaded = storage.load_cards()
    assert loaded.keys() == cards.keys()
    assert loaded["readline:Move forward one word"].to_dict() == cards["readline:Move forward one word"].to_dict()


def test_append_and_read_reviews_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    card = Card()
    _, log = Scheduler().review_card(card, Rating.Good, review_duration=1500)

    storage.append_review("readline:Foo", log)
    storage.append_review("readline:Bar", log)

    reviews = list(storage.read_reviews())
    assert [sid for sid, _ in reviews] == ["readline:Foo", "readline:Bar"]
    assert reviews[0][1].rating == Rating.Good


def test_read_reviews_empty_when_missing(tmp_path):
    storage = Storage(base_dir=tmp_path)
    assert list(storage.read_reviews()) == []


def test_aliases_empty_when_missing(tmp_path):
    storage = Storage(base_dir=tmp_path)
    assert storage.load_aliases() == {}


def test_aliases_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    aliases = {"alt+f": {"ctrl+right"}, "alt+b": {"ctrl+left"}}
    storage.save_aliases(aliases)
    assert storage.load_aliases() == aliases


def test_disabled_empty_when_missing(tmp_path):
    storage = Storage(base_dir=tmp_path)
    assert storage.load_disabled() == set()


def test_disabled_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    disabled = {"obsidian:Open graph view", "tmux:Layout: tiled"}
    storage.save_disabled(disabled)
    assert storage.load_disabled() == disabled
