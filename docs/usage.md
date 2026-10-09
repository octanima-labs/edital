# Usage and integration

## Standalone file editing

```bash
edital                             # Configured recovery, or one unnamed draft.
edital existing.txt new-file.txt    # Existing files and named drafts.
edital -R                          # Explicit recovery; draft if nothing to restore.
edital fresh.txt --no-cache         # No recovery or new caching; existing entries stay.
edital existing.txt --auto-save 1000
edital --no-cache --no-prompt        # Explicit discard without confirmation.
edital conf                        # Saved configuration takes effect on restart.
edital cache list                   # Snapshot identifiers, destinations, and UTF-8 content sizes.
edital cache purge                  # Remove snapshots, not destination files.
edital -- conf cache                # Open reserved command names as files.
```

`--recover` and `--no-cache` together are a usage error. Maintenance list/purge
commands do not launch the TUI or restore documents. `edital conf` opens only the
configuration file even when automatic restoration is enabled.
Interactive editing requires terminal input/output.
Documents are UTF-8 with uniform LF/CRLF line endings.

### File-session lifecycle

```python
from edital import Edital

editor = Edital(auto_save=0)  # Explicit settings override user YAML.
existing, named_draft = editor.open("existing.txt", "new-file.txt")
draft = editor.new()
draft.text = "Notes without a destination yet\n"
editor.save(draft, path="notes.txt")
editor.restore()             # Optional; adds snapshots without saving destination files.
editor.run()                 # Blocking terminal launch.
```

`EditalSession` owns ordered documents and active selection. `editor.files` is a
read-only tuple of `SessionFile` handles; each has an ID, optional path, current
text, and derived `modified` state. Handles address unnamed drafts unambiguously;
paths can also select open named documents. Reopening the same normalized path
selects its existing document. Opening a missing path does not create it.

Set `auto_restore=True` through configuration or the constructor to restore at
`run()` rather than explicitly calling `restore()`:

```python
editor = Edital(auto_restore=True)
editor.open("notes.txt")       # No implicit restoration yet.
editor.run()                   # Restores snapshots, then launches the TUI.
```

Calling `restore()` before automatic startup does not duplicate documents or
replace edits already made to restored buffers. `run()` leaves an empty workspace
when no documents remain; `run(create_draft=True)` requests a fallback draft only
after restoration. The CLI uses that fallback automatically.

`editor.save(document, path=...)` writes explicitly. Headless saving of an unnamed
draft without a destination raises `ValueError`; the TUI asks for Save As instead.
`save_all()` saves sequentially; a later failure does not undo successful saves.
Errors preserve unsaved buffers and keep the interactive session open.

```python
editor = Edital(cache=False)
draft = editor.new()
draft.text = "Preserve this even though automatic caching is disabled"
editor.close(draft, cache=True)  # Explicit override; does not exit the app.

editor.restore()                # Explicit API recovery is also available with cache=False.
print(editor.list(cache=True))  # Open documents plus available CacheFile snapshots.
editor.exit(cache=True)         # Whole-editor preservation and exit.
```

`close(document, cache=False)` never inherits configured caching and closing the
last tab leaves an empty workspace. `exit(cache=None)` inherits configuration;
explicit booleans override it. With prompts enabled, uncached dirty headless
close/exit raises `ConfirmationRequired` rather than launching a prompt. Set
`editor.conf.set("prompt", False)` for deliberate noninteractive discard. In the
TUI, refusal of discard confirmation keeps editing.

### Configuration and storage

Effective precedence is packaged defaults, user YAML, then explicit API/CLI
settings. Omitted settings retain defaults; zero/false overrides are respected.

```yaml
auto_save: 0
cache: true
prompt: true
auto_restore: false
```

The first standalone use creates a missing configuration from packaged defaults
and loads it. Invalid YAML/settings produce clear errors. `editor.conf.get(key,
default)` reads an effective value; `set(key, value)` validates and updates this
instance only, not the configuration file. Changing an effective autosave interval
reschedules the running timer. Settings edited on disk apply on the next launch.
`auto_restore` must be a boolean and is evaluated at editing startup. Existing user
configurations that omit it default to false without being rewritten. The sole
packaged configuration resource is `defaults.yml`; the installed user file is
still named `conf.yml`.

| Platform | Configuration | Recovery |
| --- | --- | --- |
| Linux | `$XDG_CONFIG_HOME/edital/conf.yml` | `$XDG_STATE_HOME/edital/recovery/` |
| Linux defaults | `~/.config/edital/conf.yml` | `~/.local/state/edital/recovery/` |
| Windows | `%LOCALAPPDATA%\edital\conf.yml` | `%LOCALAPPDATA%\edital\recovery\` |

Paths use native user-directory resolution without author/version prefixes.
Inspect `editor.conf.path` and `editor.cache_dir` for actual locations.

### Periodic autosave

`auto_save=0` disables autosave. Positive integer values are millisecond intervals,
not idle delays: dirty eligible files are saved even during continuous typing.
Only successful initial disk loads or explicit saves confer eligibility. Named
and unnamed drafts are skipped until explicitly saved, even if another process
creates the destination meanwhile. A failed autosave leaves dirty content intact.
**Escape only preserves or discards changes since the most recent successful
save; it cannot revert changes already written by autosave.**

### Recovery lifecycle

Escape caches unsaved documents by default, including drafts and unsaved edits to
disk-backed documents. Ctrl+W closes only the current tab and never caches it.
Snapshots persist until restored and resolved, saved, discarded,
replaced by a newer snapshot, or purged. Restoring does not immediately consume a
snapshot and does not write its destination. Fresh sessions preserve older entries.
Recovery covers orderly exits, not crashes or power loss.

`auto_restore: true` restores snapshots at ordinary CLI and API editing launches,
alongside any explicitly opened paths. `--recover` enables restoration for one CLI
launch regardless of the configured value. `--no-cache` disables both restoration
and caching for that CLI launch without removing existing snapshots. With no
opened or restored documents, the CLI creates one unnamed draft; restored sessions
do not get an extra empty tab.

The API settings are independent: `Edital(cache=False, auto_restore=True)` restores
snapshots without enabling exit caching. Use `auto_restore=False` as a constructor
override for a fresh API session. Explicit `restore()` remains available either way.

If disk still matches the saved baseline, explicitly opening and recovering the
same path produces one recovered tab. If disk changed, choose recovered text, disk
text, or a separate recovered draft. Autosave is blocked until that conflict is
resolved; choosing recovered text changes memory only. Headless callers inspect
`document.conflict` and call `editor.resolve_recovery(document, "recovered")`,
`"disk"`, or `"draft"`. Successful saving removes the associated snapshot.
`clear_cache()` removes persisted snapshots without changing open buffers.

### Standalone controls

| Key | Action |
| --- | --- |
| Ctrl+N / Ctrl+O | New draft / open path |
| Ctrl+S | Save current document; Save As for unnamed drafts |
| Ctrl+W | Close current tab without caching; confirm if dirty |
| F2 | Save and close current tab |
| F3 | Save all and exit |
| F4 | Find in current document |
| Ctrl+PageDown / Ctrl+PageUp | Next / previous tab |
| Escape | Dismiss active interaction; otherwise exit using configured caching |

Tabs preserve text, cursor, selection, and undo history. Dirty tabs show `*`, and
unresolved recovery conflicts show `!`. Unnamed labels are `draft`, `draft (1)`,
etc., without renumbering after a close. Same-named files show disambiguated paths.

## Edit text transactionally

```python
from edital import edit_text

result = edit_text("Initial notes\n", title="Notes")
if result.outcome == "accepted":
    print(result.text)
```

The session is blocking. **F2** validates and accepts the text, then closes the UI.
**Esc** cancels, asking for confirmation when the text has changed. Cancellation
does not accept or save edited text. An unchanged buffer and an empty buffer can
both be accepted explicitly.

For application integrations, `TuiEditor().edit(...)` has the same interface as
`edit_text(...)`. The public types and functions are exported by `edital`:
`EditResult`, `TuiEditor`, `Validator`, and `edit_text`.

## Supply validation

```python
from edital import TuiEditor

def validate(text: str) -> str | None:
    return None if text.strip() else "Please enter some text"

result = TuiEditor().edit("", title="Draft", validator=validate)
```

The callback is synchronous and receives the candidate's exact text. Return a
diagnostic string to reject it, or `None` to accept it. Rejection keeps the same
buffer, cursor, and undo history. Without a callback, there are no format-specific
restrictions. Unexpected callback exceptions propagate after terminal cleanup.

The caller should validate its application-specific data and install accepted
text using its own persistence policy. Embedded sessions do not load standalone
configuration, write destination files, autosave, or create recovery snapshots.

## Embedded editing controls

| Key | Action |
| --- | --- |
| F2 | Save & close |
| Esc | Cancel, or leave Find |
| F3 | Open Find; Enter finds the next occurrence, wrapping to the start |
| Ctrl-Z / Ctrl-Y | Undo / redo |
| Shift + arrows | Select text |
| F7 | Select all |

Textual provides ordinary navigation, indentation, selection, copy/cut/paste, and
terminal paste. System clipboard availability depends on the terminal.

## Fidelity and errors

Text is not parsed and reserialized. Comments, whitespace, trailing-newline
presence, and uniform LF/CRLF line endings are preserved unless edited. New
buffers default to LF. Mixed LF/CRLF and bare-CR line separators are rejected
before launch with a conversion diagnostic.

Interactive terminal input and output are required. Redirected invocations fail
clearly rather than launching an external editor. Imports are lazy, and terminal
state is restored on acceptance, cancellation, or failure.

## Confease integration

Confease is a consumer of Edital. It supplies configuration text and parser/key
validation, then installs accepted content and synchronizes its own live entries.
Configuration paths, YAML initialization headers, templates, backups, and recovery
files for those embedded transactions belong to Confease. Edital itself has no
dependency on Confease; its standalone file editor is a separate workflow.
