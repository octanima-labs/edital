# Edital

Edital provides a multi-tab terminal file editor, a standalone CLI, and a reusable
Python file-session API. Its transactional embedded API remains available for
applications that supply text and validation and own persistence themselves.

## Start here

- **Edit files in your terminal:** [install the CLI](installation.md#standalone-cli),
  then open a file with `edital notes.txt`. The [usage guide](usage.md#standalone-file-editing)
  covers saving, tabs, search, and recovery.
- **Embed an editor in your application:** [install the Python package](installation.md#python-integrations),
  then follow the [transactional editing example](usage.md#edit-text-transactionally).
  Your application validates and persists accepted text.
- **Manage files programmatically:** use the [file-session lifecycle](usage.md#file-session-lifecycle)
  and [generated API reference](api.rst). Preparation and persistence can run headlessly.
- **Resolve a problem:** see [troubleshooting](usage.md#troubleshooting) for common
  terminal, save, configuration, and recovery failures.

The API reference is generated from Python source docstrings with Sphinx. See
[local development](installation.md#local-development) for the documentation build.

```{toctree}
:maxdepth: 2

installation
usage
api
```
