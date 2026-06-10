"""Per-board project definitions.

A project module exposes ``build_blocks()`` that returns the list of
:class:`Block` instances making up the board. ``zynq_eda.core.pipeline``
discovers the project by board name (e.g. ``--board carrier``) and runs
each block through layout / route / emit.
"""
