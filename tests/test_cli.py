"""CLI dispatch and overrides without launching an interactive terminal."""

import pytest

from edital import Edital
from edital.cli import main


@pytest.fixture
def launches(monkeypatch):
    """Exercise actual facade startup while replacing only the terminal UI run."""
    from edital import editor
    from edital.file_app import FileEditorApp
    seen = []
    monkeypatch.setattr(editor.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(editor.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(FileEditorApp, "run", lambda app: seen.append(app.editor))
    return seen


def test_open_and_overrides(tmp_path, user_storage, launches):
    path = tmp_path / "new"
    assert main([str(path), "--auto-save", "0", "--no-cache", "--no-prompt"]) == 0
    editor, = launches
    assert editor.files[0].path == path
    assert not path.exists()
    assert editor.conf.get("auto_save") == 0
    assert editor.conf.get("cache") is False and editor.conf.get("prompt") is False
    user_storage[0].write_text("auto_save: 2000\ncache: false\n")
    assert main([]) == 0
    assert launches[-1].files[0].path is None
    assert launches[-1].conf.get("auto_save") == 2000 and launches[-1].conf.get("cache") is False


def test_recover_and_no_cache(launches):
    prior = Edital()
    draft = prior.new()
    draft.text = "recover me"
    prior.exit()
    assert main(["-R"]) == 0
    assert launches[-1].files[0].text == "recover me"
    assert len(launches[-1].files) == 1
    assert main(["--no-cache"]) == 0
    assert launches[-1].files[0].text == "" and len(launches[-1].cache) == 1


@pytest.mark.parametrize("arguments", [["-R", "--no-cache"], ["--auto-save", "-1"],
                                         ["--auto-save", "text"], ["cache", "unknown"]])
def test_usage_errors(arguments, user_storage):
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    assert not user_storage[0].exists()


@pytest.mark.parametrize("flag", ["-h", "--help"])
@pytest.mark.parametrize("command", [[], ["conf"], ["cache"]])
def test_help_is_complete_without_startup(command, flag, monkeypatch, capsys, user_storage):
    def forbidden(*args, **kwargs):
        raise AssertionError("Help must not initialize the editor")

    monkeypatch.setattr("edital.cli.Edital", forbidden)
    with pytest.raises(SystemExit) as error:
        main([*command, flag])
    assert error.value.code == 0
    output = capsys.readouterr()
    assert not output.err
    assert not user_storage[0].exists()
    if not command:
        for text in ("edital conf [-h]", "edital cache {list,purge} [-h]",
                     "commands:", "conf", "cache list", "cache purge",
                     "--recover", "--no-cache", "--auto-save", "--no-prompt",
                     "examples:", "edital -- conf cache"):
            assert text in output.out
    elif command == ["cache"]:
        assert "operations:" in output.out
        assert "List snapshot identifiers" in output.out
        assert "Remove all recovery snapshots" in output.out
        assert "without changing destination files" in output.out
    else:
        assert "Edit user configuration; restart to apply" in output.out


def test_configuration_and_reserved_paths(tmp_path, monkeypatch, launches):
    monkeypatch.chdir(tmp_path)
    assert main(["conf"]) == 0
    assert launches[-1].files[0].path == launches[-1].conf.path
    assert main(["--", "conf"]) == 0
    assert launches[-1].files[0].path == tmp_path / "conf"


def test_cache_commands_without_ui(tmp_path, monkeypatch, capsys):
    editor = Edital()
    draft = editor.new()
    draft.text = "α"
    editor.exit()

    def forbidden(editor, **kwargs):
        raise AssertionError("Maintenance must not start the UI")

    monkeypatch.setattr(Edital, "run", forbidden)
    assert main(["cache", "list"]) == 0
    assert "draft\t2 bytes" in capsys.readouterr().out
    assert main(["cache", "purge"]) == 0
    assert not editor.cache


def test_operational_error(monkeypatch, capsys):
    def fail(editor, **kwargs):
        raise RuntimeError("interactive terminal required")

    monkeypatch.setattr(Edital, "run", fail)
    assert main([]) == 1
    assert "interactive terminal required" in capsys.readouterr().err


def test_configured_startup_and_suppression(tmp_path, user_storage, launches):
    prior = Edital()
    draft = prior.new()
    draft.text = "remember me"
    prior.exit()
    user_storage[0].write_text("auto_restore: true\n")
    assert main([]) == 0
    assert [d.text for d in launches[-1].files] == ["remember me"]
    assert main([str(tmp_path / "explicit")]) == 0
    assert len(launches[-1].files) == 2
    assert main(["--no-cache"]) == 0
    fresh = launches[-1]
    assert len(fresh.files) == 1 and fresh.files[0].text == ""
    assert fresh.conf.get("auto_restore") is False and fresh.conf.get("cache") is False
    assert len(fresh.cache) == 1
    assert main(["conf"]) == 0
    conf_editor = launches[-1]
    assert len(conf_editor.files) == 1 and conf_editor.files[0].path == conf_editor.conf.path
    assert conf_editor.conf.get("auto_restore") is False and len(conf_editor.cache) == 1
    assert user_storage[0].read_text() == "auto_restore: true\n"


def test_empty_recovery_fallback(launches, user_storage):
    assert main(["-R"]) == 0
    assert len(launches[-1].files) == 1 and launches[-1].files[0].path is None
    user_storage[0].write_text("auto_restore: true\n")
    assert main([]) == 0
    assert len(launches[-1].files) == 1 and launches[-1].files[0].path is None
