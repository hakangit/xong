#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CONTENT_PATTERNS = (
    (
        "private IPv4 address",
        re.compile(
            r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
            r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
        ),
    ),
    (
        "private IPv6 address",
        re.compile(r"(?i)(?<![0-9a-f])(?:(?:fc|fd)[0-9a-f]{2}|fe[89ab][0-9a-f]):"),
    ),
    (
        "private DNS name",
        re.compile(
            r"(?i)\b[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\."
            r"(?:internal|local|lan|corp|home|mesh|consul)\b"
        ),
    ),
)
EMAIL_PATTERN = re.compile(
    r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\."
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)\b"
)
EXAMPLE_EMAIL_DOMAINS = {"example.com", "example.net", "example.org"}
RESERVED_EMAIL_SUFFIXES = (".example", ".invalid", ".test")
FORBIDDEN_PATH_PARTS = {".gitea", "deploy"}
FORBIDDEN_FILENAMES = {"credentials.json", "secrets.json"}
FORBIDDEN_SUFFIXES = (".nomad.hcl", ".pem", ".p12", ".pfx")


def content_violations(text: str, denylist: tuple[str, ...] = ()) -> list[str]:
    violations = {
        label for label, pattern in CONTENT_PATTERNS if pattern.search(text)
    }
    for match in EMAIL_PATTERN.finditer(text):
        domain = match.group(1).casefold()
        if domain not in EXAMPLE_EMAIL_DOMAINS and not domain.endswith(
            RESERVED_EMAIL_SUFFIXES
        ):
            violations.add("non-example email address")
    folded_text = text.casefold()
    if any(value.casefold() in folded_text for value in denylist):
        violations.add("private denylist match")
    return sorted(violations)


def path_violations(path: Path) -> list[str]:
    violations = set()
    if FORBIDDEN_PATH_PARTS.intersection(path.parts):
        violations.add("private deployment path")
    if path.name.casefold() in FORBIDDEN_FILENAMES:
        violations.add("sensitive filename")
    if path.name.casefold().endswith(FORBIDDEN_SUFFIXES):
        violations.add("sensitive file type")
    return sorted(violations)


def _tracked_files() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return [Path(value.decode()) for value in output.split(b"\0") if value]


def _denylist() -> tuple[str, ...]:
    return tuple(
        value.strip()
        for value in os.environ.get("XONG_PUBLIC_DENYLIST", "").splitlines()
        if len(value.strip()) >= 4
    )


def main() -> int:
    denylist = _denylist()
    found = False
    for relative_path in _tracked_files():
        violations = path_violations(relative_path)
        data = (ROOT / relative_path).read_bytes()
        if b"\0" not in data:
            try:
                violations.extend(content_violations(data.decode("utf-8"), denylist))
            except UnicodeDecodeError:
                pass
        if violations:
            found = True
            labels = ", ".join(sorted(set(violations)))
            print(f"public-boundary violation: {relative_path}: {labels}")
    return int(found)


if __name__ == "__main__":
    raise SystemExit(main())
