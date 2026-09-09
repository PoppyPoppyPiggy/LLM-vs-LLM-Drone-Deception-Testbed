"""Reject out-of-scope generated patches before publishing; execute no patch code."""
from pathlib import Path
import re
import subprocess


ALLOWED = re.compile(r"(?:docs/collaboration/notes/[a-zA-Z0-9_-]+\.md|(?:scripts|tests)/reporting/[a-zA-Z0-9_-]+\.(?:py|md))\Z")


def validate_entry(path, mode, status, size):
    if not ALLOWED.fullmatch(path):
        raise ValueError(f"out-of-scope path: {path}")
    if mode != "100644" or status not in ("A", "M"):
        raise ValueError(f"only added/modified regular non-executable files allowed: {path}")
    if size > 100_000:
        raise ValueError(f"file too large: {path}")


def git(*args):
    return subprocess.check_output(["git", *args])


def main():
    items = git("diff", "--cached", "--name-status", "--no-renames", "-z").decode().split("\0")
    entries = list(zip(items[0:-1:2], items[1:-1:2]))
    if not 1 <= len(entries) <= 20:
        raise ValueError("expected 1 to 20 changed files")
    total = 0
    for status, path in entries:
        if status not in ("A", "M"):
            raise ValueError(f"unsupported change: {status} {path}")
        record = git("ls-files", "--stage", "--", path).decode().split()
        mode = record[0]
        size = len(git("show", f":{path}"))
        validate_entry(path, mode, status, size)
        total += size
    if total > 500_000:
        raise ValueError("patch exceeds total content budget")
    print(f"PASS: {len(entries)} allowed files, {total} bytes; generated code was not executed")


if __name__ == "__main__":
    main()
