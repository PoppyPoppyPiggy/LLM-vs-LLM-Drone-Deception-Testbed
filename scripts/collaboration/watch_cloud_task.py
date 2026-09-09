"""Read the one configured cloud task; save private snapshots, never apply or execute."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def summarize_diff(content):
    text = content.decode("utf-8")
    paths = re.findall(r"^diff --git a/(.+) b/(.+)$", text, re.MULTILINE)
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
            "paths": [after for _, after in paths], "file_count": len(paths)}


def private_write(path, content):
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--codex-bin", default="codex")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / "docs/collaboration/bridge.json").read_text())
    task = config["task_id"]
    if not re.fullmatch(r"task_e_[0-9a-f]{32}", task):
        raise ValueError("invalid configured task ID")
    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = datetime.now(timezone.utc).isoformat()
    result = {"task_id": task, "task_url": config["task_url"], "checked_at_utc": now,
              "mode": "read_only_no_apply_no_execution", "ok": False}
    try:
        status = subprocess.run([args.codex_bin, "cloud", "status", task], capture_output=True,
                                check=True, timeout=60).stdout.decode()
        result["status"] = status.strip()
        if "[READY]" in status:
            content = subprocess.run([args.codex_bin, "cloud", "diff", task], capture_output=True,
                                     check=True, timeout=90).stdout
            if len(content) > 5_000_000:
                raise ValueError("cloud diff exceeds snapshot limit")
            result["diff"] = summarize_diff(content)
            patch = args.state_dir / (result["diff"]["sha256"] + ".patch")
            if not patch.exists():
                private_write(patch, content)
            result["patch_file"] = patch.name
        result["ok"] = True
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = "Cloud read failed; prior successful snapshots retained. Check Codex sign-in/connectivity locally."
    private_write(args.state_dir / "latest.json", (json.dumps(result, indent=2) + "\n").encode())
    print(json.dumps({k: result[k] for k in ("task_id", "checked_at_utc", "ok", "mode")}))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
