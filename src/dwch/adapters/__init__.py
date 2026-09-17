"""Concrete implementations of the application's ports.

Every port declared in `dwch.application.ports` has exactly one
adapter here (or two, in the clipboard's case, where the platform
determines which is used). Adapters are constructed once in
`dwch.cli` and passed to commands via `Deps`.
"""
