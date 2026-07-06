"""
player_images.py — download & store player avatar images from the
updateusers.php feed, deduplicated by source URL.

Images are cached under data_dir()/player_images/ using a deterministic,
collision-safe filename derived from the remote URL path (so many players
sharing a rank image only download it once). The Active-tab overlay serves
them via /api/player_image/<username>, resolved through the player DB's
stored pic_url.
"""

import os
import re
from urllib.parse import urlparse, unquote

import paths
import player_db as _db

IMAGES_DIR = os.path.join(paths.data_dir(), "player_images")

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _ensure_dir():
    os.makedirs(IMAGES_DIR, exist_ok=True)


def filename_for_url(url: str) -> str:
    """Deterministic, collision-safe local filename for a remote image URL.

    Keeps the path under /images/ (folder + basename) so e.g.
    ranks/Loan Officer.jpg and users/Mach.jpg can't clash."""
    if not url:
        return ""
    path = unquote(urlparse(url).path or "")
    key = path.split("/images/", 1)[-1] if "/images/" in path else path.lstrip("/")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", key).strip("_")
    return safe


def local_path_for_url(url: str) -> str:
    name = filename_for_url(url)
    return os.path.join(IMAGES_DIR, name) if name else ""


def has_image(url: str) -> bool:
    p = local_path_for_url(url)
    return bool(p) and os.path.exists(p)


def download_missing(pic_urls, fetch_bytes) -> int:
    """Download only images not already on disk.

    pic_urls    — iterable of remote URLs (duplicates fine).
    fetch_bytes — callable(url) -> bytes | None (None on failure/skip).

    Returns the number of new images written."""
    _ensure_dir()
    downloaded = 0
    seen = set()
    for url in pic_urls:
        if not url or url in seen:
            continue
        seen.add(url)
        name = filename_for_url(url)
        if not name:
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in _ALLOWED_EXT:
            continue
        dest = os.path.join(IMAGES_DIR, name)
        if os.path.exists(dest):
            continue
        try:
            data = fetch_bytes(url)
        except Exception:
            data = None
        if not data:
            continue
        try:
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            downloaded += 1
        except Exception:
            continue
    return downloaded


def path_for_username(username: str) -> str:
    """Local image path for a player (via their stored pic_url), or "" if none."""
    if not username:
        return ""
    url = _db.get_pic_url(username)
    if not url:
        return ""
    p = local_path_for_url(url)
    return p if p and os.path.exists(p) else ""
