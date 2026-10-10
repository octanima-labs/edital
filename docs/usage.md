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
edital cache purge                  # Confirm removal; destination files stay unchanged.
edital cache purge -f               # Unattended purge; --force is equivalent.
edital -- conf cache                # Open reserved command names as files.
```

`--recover` and `--no-cache` together are a usage error. Maintenance list/purge
commands do not launch the TUI or restore documents. `edital conf` opens only the
configuration file even when automatic restoration is enabled.
Interactive editing requires terminal input/output.
Documents are UTF-8 with uniform LF/CRLF line endings.

`edital -h` lists all commands, editing options, and examples. Use
`edital cache purge -h` for purge-specific options. Purging a nonempty cache asks
for confirmation and defaults to No; only `y` or `yes` approves removal. The prompt
shows the snapshot count and warns that cached unsaved work will be lost. Declining,
empty input, or end-of-input leaves snapshots intact. Without interactive input,
nonempty-cache purge fails unless `-f`/`--force` is supplied; it does not consume
piped input. An empty cache reports nothing to purge and succeeds without prompting.
Force belongs only to purge, not list. `--no-prompt` concerns editor discard and
does not bypass CLI purge confirmation.

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

`editor.session.move(document, index)` moves an existing document to a zero-based
position without changing the active handle, content, baseline, or recovery state.
The target must be in range; invalid/stale handles and invalid positions raise
`ValueError` before changing order. The read-only `files` tuple, tab traversal, and
save-all operations follow this order. Moving documents headlessly does not import
or launch the UI.

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
For an unnamed draft, Save As performs the write before closing its prompt. A
destination already open in another tab or an actual write failure appears inline
with the entered path retained. Correct it and retry, or cancel to keep editing.
F2 does not close the tab on failure; F3 does not exit on failure or cancellation.
Earlier successful saves during F3 remain committed.

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
focus_color: "#0178D4"
draft_color: "#FFA62B"
conflict_color: "#E06C75"
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

### Interface colors

Color settings accept hexadecimal `#RRGGBB` strings (hex letter case does not
matter). Quote them in YAML: an unquoted `#` starts a comment.

| Setting | Default | Effect |
| --- | --- | --- |
| `focus_color` | `"#0178D4"` (blue) | Focused editor/input borders, button focus indicators, and tab highlight |
| `draft_color` | `"#FFA62B"` (orange) | Text of named and unnamed never-loaded/saved drafts |
| `conflict_color` | `"#E06C75"` (red) | Text of tabs with unresolved recovery conflicts |

State-colored titles use full color when selected and a dimmed version when
inactive. A successfully saved draft returns to normal coloring; modifying an
already-saved file does not make it a draft. Enabled conflict coloring takes
precedence over enabled draft coloring, then normal theme coloring applies.
Focus indicators remain separate from title state colors and destructive actions.

Set `draft_color: null` or `conflict_color: null` to disable that state's color
override. Icons remain visible. A conflicted draft with `conflict_color: null`
still uses draft coloring when enabled; with both null, it uses normal coloring.
`focus_color` requires a color and cannot be null. Invalid formats/types report
the offending setting. Existing configuration files inherit omitted color defaults
without being rewritten.

Python constructor overrides and `conf.set` use `None` for null state colors:

```python
editor = Edital(focus_color="#88C0D0", draft_color=None, conflict_color="#FF5566")
editor.conf.set("draft_color", "#FFA62B")
editor.conf.set("conflict_color", None)
```

Valid instance color changes refresh a running standalone UI, including open
prompts, immediately without changing user YAML. Saved disk configuration still
requires a restart. Embedded transactional sessions retain theme focus styling
and do not load standalone color settings.

### Periodic autosave

`auto_save=0` disables autosave. Positive integer values are millisecond intervals,
not idle delays: dirty eligible files are saved even during continuous typing.
Only successful initial disk loads or explicit saves confer eligibility. Named
and unnamed drafts are skipped until explicitly saved, even if another process
creates the destination meanwhile. A failed autosave leaves dirty content intact.
**Exiting only preserves or discards changes since the most recent successful
save; it cannot revert changes already written by autosave.**

### Recovery lifecycle

Ctrl+Q exits and caches unsaved documents by default, including drafts and unsaved edits to
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
same path produces one recovered tab. When a destination changed, became missing,
or conflicts with another unsaved tab, the prompt offers:

- **Restore cached version**: keep cached text in memory for the original
  destination. This choice itself does not write the destination file.
- **Discard cached version**: remove the cached copy and use destination text;
  if the destination is missing, leave an empty named draft instead.
- **Keep cached version as separate draft**: detach cached text into an unnamed
  draft, retaining its snapshot association until saved/discarded. Preserve the
  destination-version tab when available; no separate file is created yet.

Escape leaves the conflict unresolved. A named draft whose destination was already
missing when cached does not become conflicting solely because it remains missing.
Rejected choices preserve cached content and unresolved state, including when
another unsaved document prevents restoring/discarding at the same path.
Autosave is blocked until the conflict is resolved. Headless callers inspect
`document.conflict` and call `editor.resolve_recovery(document, "recovered")`,
`"disk"`, or `"draft"`. Successful saving removes the associated snapshot.
`clear_cache()` removes persisted snapshots without changing open buffers. It
remains an unprompted headless API with no force parameter; confirmation is CLI-only.

### Standalone controls

| Key | Action |
| --- | --- |
| Ctrl+N / Ctrl+O | New draft / open path |
| Ctrl+S | Save current document; Save As for unnamed drafts |
| Ctrl+W | Close current tab without caching; confirm if dirty |
| F1 | Grouped, scrollable keyboard cheatsheet |
| F2 | Save and close current tab |
| F3 | Save all and exit |
| F4 | Find in current document |
| F5 | Find/Replace in current document |
| F6 / F7 | Select line / all |
| F8 | Open the scrollable session-document picker |
| Ctrl+PageDown / Ctrl+PageUp | Next / previous tab |
| Ctrl+Shift+PageUp / Ctrl+Shift+PageDown | Move active tab left / right |
| Escape | Dismiss active interaction; otherwise do nothing |
| Ctrl+Q | Exit using configured caching; confirm discard when required |

Ctrl+Q also exits from Find/Replace, but is blocked while a dialog, document
picker, or help is open. Escape dismisses the topmost interaction only; pressing
it repeatedly cannot exit the session. A declined exit confirmation preserves
the prior interaction and focus. If caching fails, a diagnostic is shown and
the session stays open for retry. Ctrl+Q exits an empty workspace too.

Tabs preserve text, cursor, selection, and undo history. Dirty tabs show **⏺**
before the name, and unresolved recovery conflicts independently show **▲**;
both states appear as `▲ ⏺ name`. Undoing back to the saved baseline removes only
the dirty marker. Resolving a conflict removes its icon and conflict coloring.
Unnamed labels are `draft`, `draft (1)`, etc., without renumbering after a close.
Same-named files show disambiguated paths.
Moving tabs stops at the ends without wrapping, preserves editing state and stable
draft labels, and keeps the active tab visible. Mouse drag-to-reorder is deferred.

### Session-document picker

Press **F8** to see all open documents in a floating list in tab order. The active
document is initially highlighted and scrolled into view. Up/Down changes the
highlight without switching the editor and stops at the ends. PageUp/PageDown
moves by a visible page; Home/End jumps to the first/last document. Enter or a
left-click on a name activates that document, closes the picker, and focuses its
editor. Escape dismisses the picker and restores your previous focus, including
an open Find/Replace input. Text, cursor, selection, and undo history are retained.

Rows show the same disambiguated names, stable draft numbering, **▲ ⏺** markers,
and state colors as tabs. Long names are truncated to keep the close control
visible. **Ctrl+W** closes the highlighted document; a left-click on the right-side
**⨯** (or compatibility **X**) closes that row's document. Both use the same close
path without activating the document or dismissing the list. Dirty/conflicted closes
use existing no-cache confirmation settings; confirmation appears above the
picker, and declining returns to the same highlighted document. Closing the
highlighted document highlights its next neighbor, or the previous neighbor at
the end. Closing the final document dismisses the picker to the empty workspace.
Failed closes report an inline error and permit retry.

**Ctrl+Shift+PageUp/PageDown** reorders the highlighted document earlier/later
without wrapping or changing the active editor document. Tab and picker order
update together, with the highlight following the moved document. Close and
reorder operations are immediate: Escape does not undo them.

F1 opens help above the picker. Help and discard confirmation must be dismissed
before browsing/reordering/closing resumes; ordinary editor save/open/exit/tab-switch commands
do not execute through the picker. Existing autosave and live color updates keep
its state markers/colors current. F8 does nothing in an empty workspace or while
another modal interaction is open, and is unavailable in embedded editing.

Left-click a tab name to select it. Left-click its right-side **⨯** to close that
document without caching, following the same confirmation rules as Ctrl+W.
Closing an inactive tab, or declining its confirmation, preserves the current
selection. Closing the final tab leaves an empty workspace. The cross falls back
to **X** for output-encoding or cell-width incompatibility; terminal font glyph
coverage cannot be detected reliably.

Confirmation and path prompts use compact, content-sized single-line buttons
side by side when space permits, with a vertical fallback on narrow terminals.

## Edit text transactionally

```python
from edital import edit_text

result = edit_text("Initial notes\n", title="Notes")
if result.outcome == "accepted":
    print(result.text)
```

The session is blocking. **F2** or **F3** validates and accepts the text, then closes the UI.
**Ctrl+Q** cancels, asking for confirmation when the text has changed. **Esc** only
dismisses the current interaction and otherwise does nothing. Cancellation
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
| F1 | Complete keyboard cheatsheet |
| F2 / F3 | Validate, accept the sole document, and close; no file is written |
| F4 | Open Find; Enter selects the next occurrence, wrapping to the start |
| F5 | Open Find/Replace |
| Esc | Dismiss active interaction; otherwise do nothing |
| Ctrl+Q | Cancel session; confirm discard if changed |
| Ctrl-Z / Ctrl-Y | Undo / redo |
| Shift + arrows | Select text |
| F6 | Select line |
| F7 | Select all |

Ctrl+Q can cancel from Find/Replace. Declining or dismissing discard confirmation
preserves the buffer, search inputs, and prior focus. Ctrl+Q is blocked while
help or confirmation is open; dismiss the topmost interaction with Escape first.

Escape no longer ends either editor; use Ctrl+Q. Embedded F3 is now acceptance,
not Find: use F4 in both modes. File/tab-only keys
(F8, Ctrl+S/N/O/W and modified PageUp/PageDown tab actions) are unavailable in embedded
document editing and are not repurposed. Ctrl+S does not accept or close. Ctrl+W
does not delete text; use Ctrl+Backspace or Alt+Backspace for previous-word deletion.
Ctrl+A retains line-start navigation; F7 selects all.

Textual provides ordinary navigation, indentation, selection, copy/cut/paste, and
terminal paste. System clipboard availability depends on the terminal.

## Find, replace, and help in both editors

F4 opens Find and F5 opens Find/Replace, retaining the search term when switching
modes. Matching defaults to literal and case-sensitive, including punctuation. Enter in
the search input or Find next selects the next occurrence and wraps at the end.
The panel reports matching results or no matches inline. Empty search is rejected.

Replace changes a valid selected match and advances. With no valid selected match,
it finds/selects one first rather than replacing unrelated selected text. An empty
replacement deletes matches. Replace all affects only the current document and
reports its count. It replaces original, non-overlapping matches without searching
inserted replacement text: changing `a` to `aa` terminates normally. One Undo restores
the entire pre-operation text, earlier editing history remains available, and Redo
reapplies the replacement. Newline conventions remain intact.

### Regular expressions

Activate **Regex: OFF** beside Find to switch to **Regex: ON**. Use Tab to reach
the button and Enter to activate it. It is available in Find and Replace, and its
setting survives closing/reopening search and changing tabs during this editor
session. Toggling clears the previous match; Replace must select a new match first.

Regex mode uses Python's `re` syntax and is case-sensitive by default. `^` and `$`
match individual line boundaries; `.` does not cross newlines. Inline flags such
as `(?i)` (ignore case) and `(?s)` (dot matches newlines) can change these defaults.
Patterns operate on normalized LF text, including in CRLF documents.

Replacement supports numbered/named captures and escapes:

| Find | Replace | Example result |
| --- | --- | --- |
| `(\w+),\s*(\w+)` | `\g<2> \g<1>` | `Doe, Jane` → `Jane Doe` |
| `(?P<word>\w+)` | `[\g<word>]` | `hello` → `[hello]` |
| `^` | `> ` | Prefix every line using Replace all |

Zero-width matches select an insertion position, with line/column feedback;
Find next advances through them before wrapping. Empty search is still rejected,
but nonempty patterns can match empty documents. Empty replacement is allowed.
Invalid patterns or replacement references appear inline without edits; an invalid
replacement does not prevent Find. Replace all uses original matches and stays
one undoable operation, including zero-width insertions.

With regex off, both inputs are literal, including backslashes. With regex on,
use `\\` in a replacement to insert one literal backslash. The standard Python
regex engine has no execution timeout here; expensive patterns can delay the UI.

Escape closes search and returns focus to editing without accepting or exiting.
Embedded replacement still requires validated F2/F3 acceptance and never writes
files, initializes standalone configuration, autosaves, or caches text.

F1 opens help even over a path, recovery, or discard dialog. It groups effective
document shortcuts, contextual controls, and mode availability; application overrides
take precedence over inherited TextArea aliases. The compact footer shows common
actions while F1 exposes hidden bindings. Scroll help with arrow keys or PageUp/
PageDown. Escape or F1 closes it, preserving the prior focus, entered values, and
editing state. Save, exit, and tab actions do not execute through the help screen.

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
