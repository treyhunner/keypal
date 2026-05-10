from fsrs import Card, Rating, Scheduler

from keypal.storage import Settings, Storage, default_data_dir


def test_default_data_dir_uses_keypal_override(monkeypatch, tmp_path):
    monkeypatch.setenv("KEYPAL_DATA_DIR", str(tmp_path))
    assert default_data_dir() == tmp_path


def test_default_data_dir_falls_back_to_platformdirs(monkeypatch):
    monkeypatch.delenv("KEYPAL_DATA_DIR", raising=False)
    # platformdirs handles XDG_DATA_HOME and platform-specific defaults.
    assert default_data_dir().name == "keypal"


def test_load_cards_returns_empty_when_missing(tmp_path):
    storage = Storage(base_dir=tmp_path)
    assert storage.load_cards() == {}


def test_save_and_load_cards_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    cards = {"readline:Move forward one word": Card()}
    storage.save_cards(cards)
    loaded = storage.load_cards()
    assert loaded.keys() == cards.keys()
    assert (
        loaded["readline:Move forward one word"].to_dict()
        == cards["readline:Move forward one word"].to_dict()
    )


def test_append_and_read_reviews_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    card = Card()
    _, log = Scheduler().review_card(card, Rating.Good, review_duration=1500)

    storage.append_review("readline:Foo", log)
    storage.append_review("readline:Bar", log)

    reviews = list(storage.read_reviews())
    assert [sid for sid, _log, _sig in reviews] == ["readline:Foo", "readline:Bar"]
    assert reviews[0][1].rating == Rating.Good
    assert reviews[0][2] == {}


def test_append_review_with_signals_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    card = Card()
    _, log = Scheduler().review_card(card, Rating.Good, review_duration=1500)
    signals = {"response_time_ms": 1500, "time_to_first_keystroke_ms": 800}

    storage.append_review("readline:Foo", log, signals=signals)

    reviews = list(storage.read_reviews())
    assert len(reviews) == 1
    assert reviews[0][2] == signals


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


def test_seen_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    seen = {"python_repl::readline:Move to start of line", "tmux::next-window"}
    storage.save_seen(seen)
    assert storage.load_seen() == seen


def test_selected_packs_returns_none_when_missing(tmp_path):
    storage = Storage(base_dir=tmp_path)
    assert storage.load_selected_packs() is None


def test_selected_packs_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    pack_ids = {"readline", "tmux", "python_repl"}
    storage.save_selected_packs(pack_ids)
    assert storage.load_selected_packs() == pack_ids


def test_settings_returns_defaults_when_missing(tmp_path):
    storage = Storage(base_dir=tmp_path)
    settings = storage.load_settings()
    assert settings == Settings()


def test_settings_roundtrip(tmp_path):
    storage = Storage(base_dir=tmp_path)
    settings = Settings(
        new_per_session=3, fast_ms=1500, slow_ms=6000, auto_advance_secs=5.0
    )
    storage.save_settings(settings)
    assert storage.load_settings() == settings


def test_settings_ignores_unknown_keys(tmp_path):
    storage = Storage(base_dir=tmp_path)
    storage.settings_path.parent.mkdir(parents=True, exist_ok=True)
    storage.settings_path.write_text('{"new_per_session": 3, "unknown_key": 42}\n')
    settings = storage.load_settings()
    assert settings.new_per_session == 3
    assert settings.fast_ms == 2_000
