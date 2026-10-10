# edital

> A text **edit**or, in the termin**al**

Edital is a multi-tab terminal file editor built on Textual, with a Python API,
periodic autosave, and recoverable unsaved documents. Its embedded text editor
accepts initial text and an optional validator and returns an explicit accepted
or cancelled result, leaving persistence to your application.

Use it for configuration drafts, notes, templates, and other workflows that need
predictable Save & close behavior without a separately installed editor.

## Installation

Requires Python 3.11 or newer. Interactive editing needs terminal input and output.

For the standalone CLI, install in an isolated environment with
[pipx](https://pipx.pypa.io/stable/installation/):

```bash
pipx install edital
```

To use the Python API, install into your application's virtual environment:

```bash
python -m pip install edital
```

Textual is installed as a dependency. See the [installation guide](docs/installation.md)
for setup, upgrades, and local development.

## First edit

```bash
edital notes.txt new-file.txt
```

Existing files open in separate tabs; missing paths open named drafts without
creating files until you save. Running `edital` without paths opens an unnamed
draft, or restores unsaved documents when automatic recovery is configured.

| Key | Action |
| --- | --- |
| **Ctrl+S** | Save the current document; choose a destination for an unnamed draft. |
| **F2** | Save and close the current tab. |
| **F3** | Save all and exit. |
| **Ctrl+Q** | Exit, caching unsaved work by default. |
| **F4 / F5** | Find / Find and Replace in the current document. |
| **F8** | Browse, select, reorder, or close session documents. |
| **F1** | Open the complete, scrollable keyboard cheatsheet. |

Escape dismisses help, search, and dialogs; it does not exit the editor.
Ctrl+W closes a tab without caching, asking for discard confirmation when needed.

```bash
edital --recover                  # Restore cached unsaved work.
edital fresh.txt --no-cache        # Disable recovery and exit caching for this launch.
edital notes.txt --auto-save 2000  # Save dirty eligible files every two seconds.
edital conf                       # Edit settings; restart to apply saved changes.
edital -- conf                    # Open a file literally named "conf".
edital --help
```

Autosave is disabled by default and applies only to documents previously loaded
from disk or explicitly saved. **Exiting or discarding does not undo changes
already autosaved.** Recovery preserves unsaved work on orderly exit, not crashes
or power loss. `--no-cache` retains existing snapshots; `edital cache list` inspects
them and `edital cache purge` asks before removing them.

See the [usage guide](docs/usage.md) for file workflows, regex replacements,
keyboard controls, and recovery conflicts.

## Python file-session API

```python
from edital import Edital

editor = Edital(auto_save=0)
documents = editor.open("notes.txt", "new-file.txt")
editor.run()  # Preparation above is headless; this launches the blocking TUI.
```

Headless callers can create a draft with `editor.new()`, assign its `.text`, and
call `editor.save(draft, path="notes.txt")`. Construction loads user settings and
initializes a missing configuration file; importing the package does not launch
a UI. `close(document, cache=True)` preserves one document; `exit(cache=True)`
preserves unsaved documents and exits the whole editor.

See [file-session lifecycle](docs/usage.md#file-session-lifecycle) and the
[API reference](docs/api.rst) for persistence, confirmation, and recovery contracts.

## Transactional embedded editor

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

**F2** or **F3** validates and accepts; **Ctrl+Q** cancels, confirming discard when
text has changed. A validator returns `None` to accept or a diagnostic string to
keep editing. Without a validator, empty text can be accepted too. Cancellation
returns no text. `TuiEditor().edit()` provides the same blocking interface.

Embedded sessions do not load standalone configuration, write files, autosave,
or cache text. Comments, whitespace, trailing-newline presence, and uniform LF
or CRLF line endings are preserved; mixed endings and bare CR are rejected.
See [embedded integration](docs/usage.md#edit-text-transactionally) for validation,
controls, and terminal requirements.

## Configuration

Run `edital conf` to edit user YAML. Explicit API/CLI settings override user YAML,
which overrides packaged defaults. For example:

```yaml
auto_save: 0
cache: true
prompt: true
auto_restore: false
```

`auto_restore: true` restores snapshots at editing startup. The Python API exposes
the actual storage locations through `editor.conf.path` and `editor.cache_dir`.
See [configuration and storage](docs/usage.md#configuration-and-storage) and
[interface colors](docs/usage.md#interface-colors) for all settings.

## Documentation

- [Installation, upgrades, and development](docs/installation.md)
- [Usage and integration](docs/usage.md)
- [API reference](docs/api.rst), generated from source docstrings with Sphinx
- [Hosted documentation](https://octanima-labs.github.io/edital/)
- [Changelog](CHANGELOG.md)

## License

MIT. See [LICENSE](LICENSE).
