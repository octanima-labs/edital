"""Validate configuration precedence and platform storage conventions."""

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
