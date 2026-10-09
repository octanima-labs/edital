"""Isolate user storage so tests never modify real settings or recovery."""

import pytest


@pytest.fixture(autouse=True)
def user_storage(tmp_path, monkeypatch):
    from edital import configuration, editor
    paths = tmp_path / "config/conf.yml", tmp_path / "state/recovery"
    monkeypatch.setattr(configuration, "storage_paths", lambda: paths)
    monkeypatch.setattr(editor, "storage_paths", lambda: paths)
    return paths
