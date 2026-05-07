from keypal.models import Pack, Shortcut
from keypal.tmux import (
    apply_tmux_overrides,
    canonical_tmux_command,
    inside_tmux,
    parse_tmux_bindings,
    tmux_to_keypal_combo,
)


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


def test_canonical_tmux_command_strips_trailing_numbers():
    assert canonical_tmux_command("resize-pane -L 2") == "resize-pane -L"
    assert canonical_tmux_command("resize-pane -L") == "resize-pane -L"
    assert canonical_tmux_command("select-pane -L") == "select-pane -L"


def test_parse_tmux_bindings_parses_typical_output():
    output = """\
bind-key    -T prefix C-h     select-pane -L
bind-key    -T prefix h       select-pane -L
bind-key -r -T prefix H       resize-pane -L 2
bind-key    -T prefix M-1     select-layout even-horizontal
bind-key    -T prefix n       next-window
"""
    bindings = parse_tmux_bindings(output=output)
    assert bindings["select-pane -L"] == ["C-h", "h"]
    assert bindings["resize-pane -L"] == ["H"]
    assert bindings["select-layout even-horizontal"] == ["M-1"]
    assert bindings["next-window"] == ["n"]


def test_apply_tmux_overrides_substitutes_keys_for_matching_commands():
    pack = Pack(
        id="tmux",
        name="t",
        description="d",
        prefix="ctrl+a",
        shortcuts=(
            Shortcut(action="Next window", keys=("n",), command="next-window"),
            Shortcut(action="Select pane left", keys=("h",), command="select-pane -L"),
            Shortcut(action="Unmatched", keys=("x",), command="totally-fake"),
        ),
    )
    bindings = {
        "next-window": ["C-n", "n"],
        "select-pane -L": ["C-h", "h"],
    }
    result = apply_tmux_overrides(pack, bindings=bindings)
    # Keys are sorted by simplicity (fewer modifiers first, then shorter).
    assert result.shortcuts[0].keys == ("n", "ctrl+n")
    assert result.shortcuts[1].keys == ("h", "ctrl+h")
    assert result.shortcuts[2].keys == ("x",)  # unmatched stays


def test_apply_tmux_overrides_noop_for_non_tmux_pack():
    pack = Pack(id="other", name="o", description="d", shortcuts=())
    result = apply_tmux_overrides(pack, bindings={"foo": ["bar"]})
    assert result is pack


def test_apply_tmux_overrides_noop_when_no_bindings():
    pack = Pack(id="tmux", name="t", description="d", prefix="ctrl+a", shortcuts=())
    result = apply_tmux_overrides(pack, bindings={})
    assert result is pack
