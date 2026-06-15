"""examples — standalone consumer projects that PROVE the reusable subsystems.

Each subpackage under ``examples/`` is an independent, hypothetical board that
consumes the project-agnostic library packages in top-level ``subsystems/`` via
the STANDARD adapter contract (``schgen.core.subsystem.Meta``). They exist to
demonstrate that a ``subsystems/<name>/`` package PORTS to another board with
ZERO changes to the library — a second consumer alongside the real ``carrier/``.
"""
