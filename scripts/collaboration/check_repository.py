"""Offline syntax and reconciliation metadata checks; never import experiment code."""
import ast
import hashlib
import json
from pathlib import Path
import re


def validate_snapshot(data):
    if data.get("schema_version") != 1:
        raise ValueError("unsupported snapshot schema")
    for source in ("local", "public_base"):
        if not re.fullmatch(r"[0-9a-f]{40}", data[source]["head_sha"]):
            raise ValueError("source needs a full Git SHA")
    paths = [row["path"] for row in data["files"]]
    if paths != sorted(set(paths)):
        raise ValueError("file paths must be unique and sorted")
    for row in data["files"]:
        path = row["path"]
        if path.startswith("/") or ".." in path.split("/") or "\\" in path:
            raise ValueError("unsafe snapshot path")
        for key in ("local_sha256", "public_sha256"):
            digest = row[key]
            if digest is not None and not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("invalid content hash")
        local, public = row["local_sha256"], row["public_sha256"]
        if local is None and public is None:
            raise ValueError("file has no source")
        expected = ("public_only" if local is None else "local_only" if public is None
                    else "identical" if local == public else "different")
        if row["comparison"] != expected:
            raise ValueError("comparison does not match hashes")


def main():
    root = Path(__file__).resolve().parents[2]
    snapshot = root / "docs/collaboration/source_inventory.json"
    data = json.loads(snapshot.read_text())
    validate_snapshot(data)
    for item in data["published_evidence"]:
        path = root / item["published_path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"published evidence changed: {item['published_path']}")
    count = 0
    for directory in ("scripts/collaboration", "tests/collaboration", "scripts/reporting", "tests/reporting"):
        for path in sorted((root / directory).glob("*.py")):
            ast.parse(path.read_text(), filename=str(path))
            count += 1
    print(f"PASS: {len(data['files'])} inventory entries; evidence hashes; {count} Python syntax checks")
    print("No experiment, generated reporting code, or live service was executed.")


if __name__ == "__main__":
    main()
