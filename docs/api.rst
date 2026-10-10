API Reference
=============

Source docstrings are the canonical reference, rendered here with Sphinx autodoc.
The file-session API owns explicit file persistence and recovery. The embedded
text editor retains caller-owned persistence. See :doc:`usage` for both workflows.

Build this reference with ``hatch run docs:build`` from the directory containing
``pyproject.toml``. Sphinx autodoc imports the Python APIs, and Napoleon renders
their Google-style docstrings. Update canonical comments in ``src/edital/``;
do not edit generated files in ``docs/_build/``. See :doc:`installation` for setup.

Embedded text API
-----------------

``Validator`` is the exported callback type ``Callable[[str], str | None]``.
It receives candidate text synchronously and returns ``None`` for acceptance
or a diagnostic string to keep editing. The canonical behavior is documented
by :func:`edital.edit_text` below; unexpected callback exceptions propagate
after terminal cleanup.

.. automodule:: edital
   :members: edit_text, TuiEditor

.. autoclass:: edital.EditResult
   :members:

File-session API
----------------

.. autoclass:: edital.Edital
   :members:

.. autoclass:: edital.EditalSession
   :members:

.. autoclass:: edital.SessionFile
   :members:

.. autoclass:: edital.CacheFile
   :members:

.. autoclass:: edital.EditalConf
   :members:

.. autoexception:: edital.ConfirmationRequired
