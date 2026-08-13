"""Optional HTTP API layer.

The demo runs entirely via the CLI with zero dependencies. This package holds an
optional FastAPI app for teams that want to drive the shell from a browser
dashboard; it is imported lazily so the core never depends on FastAPI.
"""
