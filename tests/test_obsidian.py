import json

from keypal.models import Pack, Shortcut
from keypal.obsidian import (
    apply_obsidian_overrides,
    obsidian_binding_to_combo,
    parse_obsidian_hotkeys,
)


def test_obsidian_binding_simple_modifier_letter():
    assert obsidian_binding_to_combo({"modifiers": ["Mod"], "key": "M"}) == "ctrl+m"


def test_obsidian_binding_arrow_with_alt():
    assert obsidian_binding_to_combo({"modifiers": ["Alt"], "key": "ArrowLeft"}) == "alt+left"


def test_obsidian_binding_multiple_modifiers():
    assert (
        obsidian_binding_to_combo({"modifiers": ["Alt", "Mod", "Shift"], "key": "T"})
        == "alt+ctrl+shift+t"
    )


def test_obsidian_binding_special_key_no_modifier():
    assert obsidian_binding_to_combo({"modifiers": [], "key": "Enter"}) == "enter"


def test_parse_obsidian_hotkeys_filters_empty_bindings(tmp_path):
    path = tmp_path / "hotkeys.json"
    path.write_text(json.dumps({
        "app:go-back": [{"modifiers": ["Alt"], "key": "ArrowLeft"}],
        "editor:delete-paragraph": [],
        "editor:toggle-checklist-status": [
            {"modifiers": ["Mod"], "key": "l"},
            {"modifiers": ["Mod"], "key": "Enter"},
        ],
    }))
    result = parse_obsidian_hotkeys(path)
    assert result == {
        "app:go-back": ["alt+left"],
        "editor:toggle-checklist-status": ["ctrl+l", "ctrl+enter"],
    }


def test_apply_obsidian_overrides_substitutes_matching_commands():
    pack = Pack(
        id="obsidian",
        name="o",
        description="d",
        shortcuts=(
            Shortcut(action="Navigate back", keys=("alt+left",), command="app:go-back"),
            Shortcut(action="Bold", keys=("ctrl+b",), command="editor:toggle-bold"),
            Shortcut(action="Settings", keys=("ctrl+,",), command="app:open-settings"),
        ),
    )
    hotkeys = {
        "app:go-back": ["ctrl+alt+left"],  # user remapped
        # No entry for editor:toggle-bold (default unchanged)
        # No entry for app:open-settings
    }
    result = apply_obsidian_overrides(pack, hotkeys=hotkeys)
    assert result.shortcuts[0].keys == ("ctrl+alt+left",)
    assert result.shortcuts[1].keys == ("ctrl+b",)
    assert result.shortcuts[2].keys == ("ctrl+,",)


def test_apply_obsidian_overrides_noop_for_non_obsidian_pack():
    pack = Pack(id="other", name="o", description="d", shortcuts=())
    result = apply_obsidian_overrides(pack, hotkeys={"foo": ["bar"]})
    assert result is pack
