from keypal.models import Pack, Shortcut, builtin_packs, load_pack, parse_pack


def test_parse_pack_minimal():
    data = {
        "pack": {
            "id": "test",
            "name": "Test Pack",
            "description": "A test pack",
        },
        "shortcuts": [
            {"action": "Do thing", "keys": ["ctrl+a"]},
        ],
    }
    pack = parse_pack(data)
    assert pack == Pack(
        id="test",
        name="Test Pack",
        description="A test pack",
        shortcuts=(Shortcut(action="Do thing", keys=("ctrl+a",)),),
    )


def test_parse_pack_optional_fields():
    data = {
        "pack": {"id": "t", "name": "T", "description": "d"},
        "shortcuts": [
            {
                "action": "Open menu",
                "keys": ["f10", "alt+space"],
                "tags": ["nav"],
                "hint": "Top of screen",
            },
        ],
    }
    pack = parse_pack(data)
    [shortcut] = pack.shortcuts
    assert shortcut.keys == ("f10", "alt+space")
    assert shortcut.tags == ("nav",)
    assert shortcut.hint == "Top of screen"


def test_parse_pack_no_shortcuts():
    data = {"pack": {"id": "empty", "name": "E", "description": "d"}}
    pack = parse_pack(data)
    assert pack.shortcuts == ()


def test_load_pack_from_file(tmp_path):
    toml = """
[pack]
id = "x"
name = "X"
description = "x desc"

[[shortcuts]]
action = "Foo"
keys = ["ctrl+f"]
"""
    path = tmp_path / "x.toml"
    path.write_text(toml)
    pack = load_pack(path)
    assert pack.id == "x"
    assert pack.shortcuts[0].action == "Foo"


def test_builtin_packs_includes_readline():
    packs = builtin_packs()
    by_id = {pack.id: pack for pack in packs}
    assert "readline" in by_id
    readline = by_id["readline"]
    assert readline.name == "Readline / Bash"
    assert any(s.action == "Move to start of line" for s in readline.shortcuts)


def test_parse_pack_with_prefix():
    data = {
        "pack": {
            "id": "tmux",
            "name": "tmux",
            "description": "tmux shortcuts",
            "prefix": "ctrl+a",
        },
        "shortcuts": [{"action": "Next window", "keys": ["n"]}],
    }
    pack = parse_pack(data)
    assert pack.prefix == "ctrl+a"


def test_parse_pack_prefix_defaults_to_none():
    data = {
        "pack": {"id": "x", "name": "x", "description": "x"},
        "shortcuts": [{"action": "a", "keys": ["b"]}],
    }
    assert parse_pack(data).prefix is None


def test_shortcut_id_format():
    pack = Pack(
        id="readline",
        name="n",
        description="d",
        shortcuts=(Shortcut(action="Move to start", keys=("ctrl+a",)),),
    )
    assert pack.shortcut_id(pack.shortcuts[0]) == "readline:Move to start"
