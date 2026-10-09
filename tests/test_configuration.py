"""Validate configuration precedence and platform storage conventions."""

import subprocess
import sys
from importlib.resources import files

import pytest
from platformdirs.unix import Unix
from platformdirs.windows import Windows

from edital.configuration import EditalConf, storage_paths


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    from edital import configuration
    paths = tmp_path / "config" / "conf.yml", tmp_path / "state" / "recovery"
    monkeypatch.setattr(configuration, "storage_paths", lambda: paths)
    return paths


def test_defaults_and_layering(isolated_storage):
    path, _ = isolated_storage
    conf = EditalConf()
    assert conf.get("auto_save") == 0
    assert conf.get("cache") is True
    assert conf.get("auto_restore") is False
    assert path.read_text() == files("edital").joinpath("defaults.yml").read_text()
    path.write_text("auto_save: 1000\n")
    conf = EditalConf(auto_save=0, cache=False)
    assert conf.get("auto_save") == 0
    assert conf.get("cache") is False
    assert conf.get("prompt") is True
    conf.set("prompt", False)
    assert conf.get("prompt") is False
    assert conf.get("missing", 42) == 42
    assert path.read_text() == "auto_save: 1000\n"


@pytest.mark.parametrize("text", ["[invalid", "- list", "auto_save: -1", "auto_save: true",
                                       "auto_save: 1.5", "cache: 1", "prompt: no-string", "unknown: 1",
                                       "auto_restore: 1", "auto_restore: text"])
def test_invalid_settings(isolated_storage, text):
    path, _ = isolated_storage
    path.parent.mkdir()
    path.write_text(text)
    with pytest.raises(ValueError):
        EditalConf()


def test_native_paths(tmp_path, monkeypatch):
    from edital import configuration
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(configuration, "PlatformDirs", Unix)
    assert storage_paths() == (tmp_path / "config/edital/conf.yml", tmp_path / "state/edital/recovery")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    from platformdirs import windows
    monkeypatch.setattr(windows, "get_win_folder", lambda name: str(tmp_path / "local"))
    monkeypatch.setattr(configuration, "PlatformDirs", Windows)
    config, recovery = storage_paths()
    assert config == tmp_path / "local/edital/conf.yml"
    assert recovery == tmp_path / "local/edital/recovery"


def test_auto_restore_precedence_and_instance_update(isolated_storage):
    path, _ = isolated_storage
    EditalConf()
    path.write_text("auto_restore: true\n")
    assert EditalConf().get("auto_restore") is True
    conf = EditalConf(auto_restore=False)
    assert conf.get("auto_restore") is False
    conf.set("auto_restore", True)
    assert conf.get("auto_restore") is True
    assert path.read_text() == "auto_restore: true\n"


def test_color_defaults_precedence_and_live_notifications(isolated_storage):
    path, _ = isolated_storage
    EditalConf()
    path.write_text('conflict_color: "#abcdef"\ndraft_color: null\n')
    conf = EditalConf(conflict_color=None)
    assert conf.get("focus_color") == "#0178D4"
    assert conf.get("draft_color") is None
    assert conf.get("conflict_color") is None
    notified = []
    unsubscribe = conf.subscribe(notified.append)
    conf.set("draft_color", "#aBcD01")
    conf.set("focus_color", "#123456")
    conf.set("conflict_color", None)
    assert notified == ["draft_color", "focus_color", "conflict_color"]
    assert conf.get("draft_color") == "#aBcD01"
    unsubscribe()
    assert path.read_text() == 'conflict_color: "#abcdef"\ndraft_color: null\n'


@pytest.mark.parametrize("key", ["focus_color", "draft_color", "conflict_color"])
@pytest.mark.parametrize("value", [True, 123, [], "red", "#123", "#12345g", "#1234567"])
def test_invalid_colors(isolated_storage, key, value):
    conf = EditalConf()
    previous = conf.get(key)
    with pytest.raises(ValueError, match=key + " must be.*#RRGGBB"):
        conf.set(key, value)
    assert conf.get(key) == previous


def test_focus_color_cannot_be_null(isolated_storage):
    with pytest.raises(ValueError, match="focus_color"):
        EditalConf(focus_color=None)


def test_color_configuration_does_not_import_textual(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    result = subprocess.run(
        [sys.executable, "-c", ("from edital import Edital; import sys; "
         "editor = Edital(focus_color='#123456', draft_color=None, conflict_color=None); "
         "assert editor.conf.get('draft_color') is None; assert 'textual' not in sys.modules")],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
