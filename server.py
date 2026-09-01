#!/usr/bin/env python3
"""Hermes Studio v5.0 — Thin launcher."""
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

from hermes.server import app, web

if __name__ == "__main__":
    from hermes.core import PORT, CFG
    web.run_app(app, host=CFG["server"]["host"], port=PORT, print=None)
