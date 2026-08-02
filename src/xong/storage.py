"""File storage on the persistent storage volume.

Layout under the volume root (get_files_dir()):

    <username>/<task_id>/<uuid>-<safe-filename>

Every user gets their own top-level subfolder, so the tree is browsable and
segregated per person on the shared filesystem. The DB stores only the
relative path; bytes never touch Postgres.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import shutil
from pathlib import Path

from xong.config import get_files_dir

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_component(name: str, fallback: str) -> str:
    # collapse anything non-portable to "_"; never allow empty / dotfiles /
    # traversal. Applied to every path segment we build.
    cleaned = _SAFE.sub("_", (name or "").strip()).strip("._")
    return cleaned[:200] or fallback


def build_rel_path(username: str, task_id: int, filename: str) -> str:
    user_dir = _safe_component(username, "user")
    safe_name = _safe_component(filename, "file")
    token = secrets.token_hex(8)
    return f"{user_dir}/{task_id}/{token}-{safe_name}"


def _abs(rel_path: str) -> Path:
    root = Path(get_files_dir()).resolve()
    target = (root / rel_path).resolve()
    # defence in depth: the resolved path must stay under the root even if a
    # stored path were ever tampered with.
    if root not in target.parents and target != root:
        raise ValueError("path escapes storage root")
    return target


def save_stream(rel_path: str, src) -> int:
    dst = _abs(rel_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(dst, "wb") as out:
        while True:
            chunk = src.read(1024 * 256)
            if not chunk:
                break
            size += len(chunk)
            out.write(chunk)
    return size


def open_read(rel_path: str):
    return open(_abs(rel_path), "rb")


def delete(rel_path: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.remove(_abs(rel_path))


def delete_task_dir(username: str, task_id: int) -> None:
    d = _abs(f"{_safe_component(username, 'user')}/{task_id}")
    shutil.rmtree(d, ignore_errors=True)
