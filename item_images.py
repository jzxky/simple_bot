"""
item_images.py — cache of the game's item artwork (bionics, weapons, vehicles,
apartments) shown in the Profile tab.

Files live under data_dir()/item_images/ and are named with
player_images.filename_for_url, so the profile parser can hand the UI a key
before the image has been downloaded. Served via /api/item_image/<key>.
"""

import os
import re

import paths
import player_images as _pi

IMAGES_DIR = os.path.join(paths.data_dir(), "item_images")

_SAFE_KEY = re.compile(r"^[A-Za-z0-9._-]+$")


def key_for_url(url: str) -> str:
    return _pi.filename_for_url(url)


def path_for_key(key: str) -> str:
    """Local path of a cached image, or "" if the key is unsafe or not cached."""
    if not key or not _SAFE_KEY.match(key) or key.startswith("."):
        return ""
    p = os.path.join(IMAGES_DIR, key)
    return p if os.path.exists(p) else ""


def download_missing(urls, fetch_bytes) -> int:
    return _pi.download_missing(urls, fetch_bytes, IMAGES_DIR)
