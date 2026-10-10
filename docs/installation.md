# Installation

Edital requires Python 3.11 or newer and installs Textual as a Python dependency.
No external editor executable is required. Editing needs interactive terminal
input and output; importing the package does not initialize a terminal UI.

## Standalone CLI

Install [pipx](https://pipx.pypa.io/stable/installation/) first if needed, then
install Edital into its own isolated environment:

```bash
pipx install edital
edital --help
edital notes.txt
```

If the command is not found after installation, run `pipx ensurepath` and open a
new terminal. Press Ctrl+S to save your first document, or F2 to save and close it.
See the [usage guide](usage.md) for controls and recovery behavior.

## Python integrations

Install Edital into your application's virtual environment. A pipx installation
exposes the CLI but does not make the package importable in other environments.

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install edital
python -c "from edital import Edital, edit_text; print('Edital imports successfully')"
```

You can also run the CLI from this environment with `edital` or `python -m edital`.
Headless file operations do not need a terminal. `Edital()` does read user YAML
and initialize a missing configuration file; importing `edital` and embedded
`edit_text()` sessions do not initialize standalone configuration.

## Upgrading

Use the command corresponding to your installation method:

```bash
pipx upgrade edital
# Or, in your application's environment:
python -m pip install --upgrade edital
```

Review the [changelog](https://github.com/octanima-labs/edital/blob/main/CHANGELOG.md)
before upgrading. Existing configuration files retain their contents; omitted
settings inherit packaged defaults. Finish the current editing session and
relaunch to use the updated package.

## Terminal and file requirements

- Interactive editing requires both stdin and stdout to be terminals; piping or
  redirecting an editing invocation is unsupported. Cache maintenance commands
  do not launch the TUI.
- Files must be UTF-8 with uniform LF or CRLF line endings. Mixed line endings and
  bare CR separators are rejected instead of silently converted.
- Terminal paste is supported; operating-system clipboard integration depends
  on your terminal.

## Local development

Install [Hatch](https://hatch.pypa.io/latest/install/) and Git, then clone the
public repository:

```bash
git clone https://github.com/octanima-labs/edital.git
cd edital
hatch run edital --help
```

Run project commands from the directory containing `pyproject.toml`. In the
two-workspace development layout, this is `public/`; in a public-repository
checkout, it is the repository root.

```bash
hatch run pytest tests/test_cli.py
hatch run ruff check .
hatch run mypy src
hatch run docs:build
hatch build
```

The package includes a `py.typed` marker so consumers can type-check integrations.
Choose focused tests for the behavior being changed; use `hatch run pytest` when
you intentionally need the full suite. To install a checkout into another Python
environment, use `python -m pip install -e /path/to/project` with the directory
containing `pyproject.toml`.

`hatch run docs:build` generates the Sphinx HTML documentation at
`docs/_build/html/index.html` and treats warnings as errors. API pages are rendered
from source docstrings; edit those docstrings rather than generated HTML.
