#!/usr/bin/env python
"""
Entry point for running symclatron as a module.

This allows running symclatron with:
python -m symclatron [commands]
"""

from .symclatron import app

if __name__ == "__main__":
    app()
