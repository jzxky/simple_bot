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


def earn_catalog_path() -> str:
    """Writable earn catalog (earn_catalog.json, gitignored).

    available_earns.json is the tracked seed and is never written at runtime —
    a dirty tracked file would block `git pull` updates. On first use the
    catalog is copied from it (the data-dir copy first, so installs that
    already wrote their catalog there keep it)."""
    path = os.path.join(data_dir(), "earn_catalog.json")
    if not os.path.exists(path):
        import shutil
        for base in (data_dir(), resource_dir()):
            seed = os.path.join(base, "available_earns.json")
            if os.path.exists(seed):
                try:
                    shutil.copyfile(seed, path)
                except OSError:
                    pass
                break
    return path
