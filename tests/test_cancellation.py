"""Caller-owned cancellation across public APIs and UI lifecycle boundaries."""

import asyncio
import subprocess
import sys
from threading import Event, Thread

import pytest
from textual.widgets import TextArea

import edital
from edital import EditResult, TuiEditor, edit_text
from edital.app import DiscardDialog, EditorApp
from edital.controls import HelpDialog
from edital.search import SearchPanel


@pytest.mark.parametrize("adapter", [False, True])
def test_precancelled_without_terminal_or_ui_import(adapter):
    source = f"""
import sys
from threading import Event
from edital import EditResult, TuiEditor, edit_text
event = Event()
event.set()
edit = TuiEditor().edit if {adapter!r} else edit_text
assert not sys.stdin.isatty()
assert edit('seed', cancel_event=event) == EditResult('cancelled')
assert event.is_set()
assert 'textual' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", source], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("text", ["a\r\nb\nc", "a\rb"])
@pytest.mark.parametrize("edit", [edit_text, TuiEditor().edit])
def test_precancellation_preserves_text_validation(text, edit):
    event = Event()
    event.set()
    with pytest.raises(ValueError, match="line endings"):
        edit(text, cancel_event=event)
    assert event.is_set()


@pytest.mark.parametrize("edit", [edit_text, TuiEditor().edit])
def test_event_forwarded_and_startup_race(monkeypatch, edit):
    event = Event()
    original_init = EditorApp.__init__

    def initialize(app, *args, **kwargs):
        assert kwargs["cancel_event"] is event
        original_init(app, *args, **kwargs)
        # Signal after the public wrapper's pre-start check, before mount.
        event.set()

    def run(app):
        async def exercise():
            async with app.run_test():
                pass
            return app.return_value
        return asyncio.run(exercise())

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(EditorApp, "__init__", initialize)
    monkeypatch.setattr(EditorApp, "run", run)
    assert edit("seed", cancel_event=event) == EditResult("cancelled")
    assert event.is_set()


@pytest.mark.parametrize("changed", [False, True])
@pytest.mark.parametrize("interaction", ["none", "find", "replace", "help", "discard"])
def test_thread_cancellation_discards_every_interaction(changed, interaction, user_storage):
    async def exercise():
        event = Event()
        app = EditorApp("seed", cancel_event=event,
                        validator=lambda _: pytest.fail("Cancellation must not validate"))
        async with app.run_test() as pilot:
            if changed or interaction == "discard":
                await pilot.press("x")
            if interaction in ("find", "replace"):
                await pilot.press("f4" if interaction == "find" else "f5")
                assert app.query_one(SearchPanel).display
            elif interaction == "help":
                await pilot.press("f1")
                assert isinstance(app.screen, HelpDialog)
            elif interaction == "discard":
                await pilot.press("ctrl+q")
                assert isinstance(app.screen, DiscardDialog)
            thread = Thread(target=event.set)
            thread.start()
            thread.join(timeout=2)
            assert not thread.is_alive()
            async with asyncio.timeout(5):
                while app.return_value is None:
                    await asyncio.sleep(0.01)
            assert app.return_value == EditResult("cancelled")
        assert event.is_set()
        assert not user_storage[0].exists() and not user_storage[1].exists()
    asyncio.run(exercise())


def test_cancellation_before_acceptance_skips_validation():
    async def exercise():
        event = Event()
        app = EditorApp("seed", cancel_event=event,
                        validator=lambda _: pytest.fail("Must not validate"))
        async with app.run_test():
            event.set()
            app.action_accept()
        assert app.return_value == EditResult("cancelled")
    asyncio.run(exercise())


@pytest.mark.parametrize("diagnostic", [None, "rejected"])
def test_cancellation_during_validation(diagnostic):
    async def exercise():
        event, validating = Event(), Event()

        def watch():
            if validating.wait(timeout=5):
                event.set()

        def validate(_):
            validating.set()
            assert event.wait(timeout=5), "Watcher did not signal cancellation"
            return diagnostic

        thread = Thread(target=watch)
        thread.start()
        try:
            app = EditorApp("seed", cancel_event=event, validator=validate)
            async with app.run_test():
                app.action_accept()
            assert app.return_value == EditResult("cancelled")
        finally:
            validating.set()
            thread.join(timeout=5)
    asyncio.run(exercise())


def test_validator_exception_during_cancellation_propagates(monkeypatch):
    event = Event()
    failure = RuntimeError("validator failed")

    def validate(_):
        event.set()
        raise failure

    def run(app):
        async def exercise():
            async with app.run_test():
                app.action_accept()
            assert app.return_value == EditResult("cancelled")
            return app.return_value
        return asyncio.run(exercise())

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(EditorApp, "run", run)
    with pytest.raises(RuntimeError) as caught:
        edital.edit_text("seed", validator=validate, cancel_event=event)
    assert caught.value is failure


def test_acceptance_is_not_overwritten_by_late_cancellation():
    async def exercise():
        event = Event()
        calls = []
        app = EditorApp("seed", cancel_event=event, validator=lambda text: calls.append(text))
        async with app.run_test():
            app.action_accept()
            event.set()
            app._check_cancelled()
            app.action_accept()
            await app.action_quit()
        assert calls == ["seed"]
        assert app.return_value == EditResult("accepted", "seed")
    asyncio.run(exercise())


def test_repeated_cancellation_and_late_discard_callback(monkeypatch):
    async def exercise():
        event = Event()
        app = EditorApp("seed", cancel_event=event,
                        validator=lambda _: pytest.fail("Must not validate"))
        async with app.run_test() as pilot:
            await pilot.press("x")
            callbacks = []
            original = app.push_screen

            def push(screen, callback):
                callbacks.append(callback)
                return original(screen, callback)

            monkeypatch.setattr(app, "push_screen", push)
            await app.action_quit()
            await pilot.pause()
            assert isinstance(app.screen, DiscardDialog)
            event.set()
            app._check_cancelled()
            app._check_cancelled()
            callbacks[0](False)
            callbacks[0](True)
            app.action_accept()
        assert app.return_value == EditResult("cancelled")
    asyncio.run(exercise())


def test_unset_event_preserves_interactive_discard():
    async def exercise():
        event = Event()
        app = EditorApp("seed", cancel_event=event)
        async with app.run_test() as pilot:
            await pilot.press("x", "ctrl+q")
            assert isinstance(app.screen, DiscardDialog)
            await pilot.click("#keep")
            assert app.return_value is None
            assert app.query_one(TextArea).text == "xseed"
            await pilot.press("f2")
        assert app.return_value == EditResult("accepted", "xseed")
        assert not event.is_set()
    asyncio.run(exercise())
