# Installation

Edital requires Python 3.11 or newer and installs Textual as a Python dependency.
No external editor executable is required. Editing needs interactive terminal
input and output; importing the package does not initialize a terminal UI.

The package is not published yet. Install from the public project directory:

```bash
python -m pip install -e /path/to/edital/public
```

After publication, install using the package name `edital`:

```bash
python -m pip install edital
```

## Development

Run tests, lint, type checks, docs, and builds from `public/`:

```bash
hatch run pytest
hatch run ruff check .
hatch run mypy src
hatch run docs:build
hatch build
```

The package includes a `py.typed` marker so consumers can type-check integrations.
