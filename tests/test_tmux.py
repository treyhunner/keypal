from keypal.tmux import inside_tmux, tmux_to_keypal_combo


def test_inside_tmux_when_env_set(monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux-1000/default,123,0")
    assert inside_tmux() is True


def test_inside_tmux_when_env_missing(monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    assert inside_tmux() is False


def test_tmux_to_keypal_combo_simple_modifiers():
    assert tmux_to_keypal_combo("C-a") == "ctrl+a"
    assert tmux_to_keypal_combo("M-x") == "alt+x"
    assert tmux_to_keypal_combo("S-Tab") == "shift+tab"


def test_tmux_to_keypal_combo_stacked_modifiers():
    assert tmux_to_keypal_combo("C-S-a") == "ctrl+shift+a"
    assert tmux_to_keypal_combo("M-C-Left") == "alt+ctrl+left"


def test_tmux_to_keypal_combo_no_modifiers():
    assert tmux_to_keypal_combo("F12") == "f12"
    assert tmux_to_keypal_combo("Space") == "space"


def test_tmux_to_keypal_combo_empty():
    assert tmux_to_keypal_combo("") == ""
