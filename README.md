# edital

> A text **edit**or, in the termin**al**

Edital is a multi-tab terminal file editor built on Textual, with a Python API,
periodic autosave, and recoverable unsaved documents. Its embedded text editor
also accepts initial text and an optional validator and returns an explicit
accepted or cancelled result, leaving persistence to your application.

Use it for configuration drafts, notes, templates, and other workflows that need
predictable Save & close behavior without a separately installed editor.

## Installation

Requires Python 3.11 or newer. Textual is installed as a dependency. Interactive
editing needs terminal input and output; imports do not initialize Textual.

Edital is not published yet. Install your local checkout:

```bash
python -m pip install -e /path/to/edital/public
```

After publication, the package name will be `edital`:

```bash
python -m pip install edital
```

## Usage

### Standalone editor

```bash
edital notes.txt new-file.txt
edital --recover                  # Restore previously cached unsaved documents.
edital fresh.txt --no-cache        # Fresh session; existing snapshots are retained.
edital notes.txt --auto-save 2000  # Save dirty eligible files every two seconds.
edital conf                       # Edit settings; restart to apply saved changes.
edital cache list
edital cache purge                # Confirm before removing cached unsaved work.
edital cache purge --force        # Skip confirmation (required for unattended use).
edital -- conf                    # Open a file literally named "conf".
```

No paths opens recovered documents when requested or configured, otherwise an
unnamed draft. Missing paths open named drafts, without creating
files until an explicit save. **F2** saves and closes the current tab, **F3** saves
all and exits, **F4** opens Find, and **F5** opens Find/Replace. **F1** opens a
scrollable cheatsheet with all bindings, including editing shortcuts hidden from
the footer. **Escape** dismisses help, dialogs, or search first, then exits.
Ctrl+S saves, Ctrl+W closes a tab without caching, Ctrl+N creates a draft,
Ctrl+O opens a file, and Ctrl+PageUp/PageDown switches tabs.
**Ctrl+Shift+PageUp/PageDown** moves the active tab left/right without wrapping or
losing its cursor, selection, or undo history. Mouse dragging is deferred.

Find/Replace defaults to literal, case-sensitive text in the current document.
The **Regex: OFF/ON** button beside Find enables Python regular expressions and
replacement captures: find `(\w+),\s*(\w+)` and replace with `\g<2> \g<1>` to turn
`Doe, Jane` into `Jane Doe`. The setting is retained for the current editor session.
Find next selects a match and wraps; Replace changes the selected match, and
Replace all reports a count and can be undone in one step. An empty replacement
deletes matches. Save As keeps its prompt and entered path open on errors, so you
can correct a duplicate destination or filesystem failure and retry.

Left-click a tab name to select it or its right-side **⨯** to close that document
without caching (with discard confirmation when enabled). Closing an inactive tab
keeps your current document selected. The close control falls back to **X** when
encoding or terminal cell-width compatibility requires it.
Tab prefixes **⏺** (modified) and **▲** (unresolved recovery conflict) can appear
together. Draft titles are orange by default; conflict titles are red. Inactive
state-colored titles are dimmed, and successful first saves remove draft coloring.

By default, autosave is disabled, exit caches unsaved work, and uncached discard
requires confirmation. Enable recovery for one launch with `--recover`, or set
`auto_restore: true` to restore at every editing startup. `--no-cache` suppresses
both restoration and caching. Recovery covers orderly exit, not crashes.
Autosave only applies to files loaded from disk or explicitly
saved. **Escape does not undo content already autosaved.**

Recovery conflicts offer **Restore cached version**, **Discard cached version**,
or **Keep cached version as separate draft**, with explanations for each choice.
Restoring changes memory, not the destination file. A separate draft is unnamed
and must be saved explicitly. CLI cache purge defaults to No; the headless
`editor.clear_cache()` API remains unprompted.

### File-session API

```python
from edital import Edital

editor = Edital(auto_save=0)
documents = editor.open("notes.txt", "new-file.txt")
editor.run()  # Preparation above is headless; this launches the blocking TUI.
```

For headless use, create a draft with `editor.new()`, assign its `.text`, then call
`editor.save(draft, path="notes.txt")`. `close(document, cache=True)` caches one
document; `exit(cache=True)` caches unsaved documents and exits the whole editor.
See the [usage guide](docs/usage.md) for lifecycle and recovery details.

### Configuration

Explicit API/CLI settings override user YAML, which overrides packaged defaults:

```yaml
auto_save: 0
cache: true
prompt: true
auto_restore: false
focus_color: "#0178D4"
draft_color: "#FFA62B"
conflict_color: "#E06C75"
```

Colors use quoted `"#RRGGBB"` strings. `focus_color` controls editor/input focus
borders, button focus indicators, and the tab highlight. `draft_color: null` or
`conflict_color: null` disables that state's text-color override without hiding
icons. Enabled conflict coloring takes precedence over enabled draft coloring,
then normal tab coloring applies. Both named and unnamed never-saved drafts use
draft coloring. `focus_color` cannot be null.

Constructor overrides accept Python `None` for state colors. Instance-only
changes apply immediately in a running standalone UI without rewriting user YAML:

```python
editor = Edital(conflict_color=None)
editor.conf.set("focus_color", "#88C0D0")
editor.conf.set("draft_color", None)
```

Linux uses `$XDG_CONFIG_HOME/edital/conf.yml` and
`$XDG_STATE_HOME/edital/recovery/`, defaulting to `~/.config` and `~/.local/state`.
Windows uses `%LOCALAPPDATA%\edital\conf.yml` and
`%LOCALAPPDATA%\edital\recovery\`. The API exposes `editor.conf.path` and
`editor.cache_dir`. A missing configuration is initialized on first standalone use.

`Edital(auto_restore=True).run()` also restores at startup; construction and
`open()` do not. Explicit `restore()` remains available, and calling it before
automatic startup does not duplicate documents. `edital conf` opens only the
configuration file regardless of `auto_restore`.

### Transactional embedded editor

```python
from edital import edit_text

result = edit_text(
    "Initial notes\n",
    title="Notes",
    validator=lambda text: None if text.strip() else "Please enter some text",
)
if result.outcome == "accepted":
    print(result.text)  # Your application chooses how to save it.
```

Without a validator, arbitrary text, including empty text, can be accepted.
`EditResult("accepted", "")` differs from `EditResult("cancelled")`.
`TuiEditor.edit()` exposes the same blocking session interface for integrations.
Import these APIs directly from `edital`.

### Shared controls

| Key | Action |
| --- | --- |
| **F1** | Scrollable keyboard cheatsheet; Escape or F1 returns to the prior interaction. |
| **F2** | Save and close the standalone tab; validate and accept embedded text. |
| **F3** | Save all and exit standalone; validate and accept the sole embedded document. |
| **F4** | Find text; Enter selects the next occurrence, wrapping to the start. |
| **F5** | Find/Replace, including Replace all in the current document. |
| **Esc** | Dismiss the active interaction; otherwise exit standalone or cancel embedded. |
| **Ctrl-Z / Ctrl-Y** | Undo / redo. |
| **Shift + arrows** | Select text. |
| **F6** | Select line. |
| **F7** | Select all. |

**Compatibility note:** embedded Find moved from F3 to F4. F3 now accepts text
after validation, just like F2. Embedded Ctrl+S is unavailable and does not accept
or close; Ctrl+W is reserved and no longer deletes a word. File/tab actions remain
standalone-only. Use Ctrl+Backspace or Alt+Backspace to delete the previous word
in either editor. Ctrl+A moves to line start; use F7 for Select all.

Selection, copy/cut/paste, navigation, and indentation use Textual's TextArea.
Terminal paste is supported; operating-system clipboard integration depends on
the terminal and is not universally guaranteed.

### Validation and text fidelity

A validator is a synchronous callback receiving candidate text. Return `None` to
accept it or a diagnostic string to reject it. Rejection keeps text, cursor, and
undo history intact in the same editing session. Unexpected validator exceptions
propagate after terminal cleanup.

Edital preserves comments, whitespace, trailing-newline presence, and uniform LF
or CRLF line endings. New text defaults to LF. Mixed LF/CRLF or bare-CR separators
are rejected before launch rather than silently normalized. Embedded editing does
not parse document formats, write files, cache text, or infer acceptance from
filesystem metadata.

Cancellation returns a cancelled result, not edited text. Running without
interactive terminal input and output raises an actionable error. Terminal state
is restored on acceptance, cancellation, and failure.

### Local development

Run these commands from `public/`:

```bash
hatch run pytest
hatch run ruff check .
hatch run mypy src
hatch run docs:build
hatch build
```

## Documentation

- [Usage and integration](docs/usage.md)
- [API reference](docs/api.rst), generated from source docstrings with Sphinx

## License

MIT. See [LICENSE](LICENSE).
