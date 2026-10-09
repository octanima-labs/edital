API Reference
=============

Source docstrings are the canonical reference, rendered here with Sphinx autodoc.
The file-session API owns explicit file persistence and recovery. The embedded
text editor retains caller-owned persistence. See :doc:`usage` for both workflows.

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
