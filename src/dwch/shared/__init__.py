"""Cross-cutting utilities used by every layer.

Only `errors` lives here today. Kept separate from `domain` because
the error hierarchy is imported by both `domain` and `adapters`, and
neither should have to reach into the other's package to find it.
"""
