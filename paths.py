"""
Path helpers that work both when running from source and when frozen by PyInstaller.
"""

import os
import sys


def resource_dir() -> str:
    """Bundled read-only assets (templates, static files)."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
    """Writable user data directory (config.json, .env, .browser_profile)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
