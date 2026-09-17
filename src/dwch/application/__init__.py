"""Application layer: ports, orchestration, and commands.

Depends on `domain` and `shared`, but not on `adapters` or `cli`.
Concrete adapter instances are injected via `deps.Deps`.
"""
