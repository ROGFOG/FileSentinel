"""Portable file-integrity snapshots. Python 3.12+, no third-party packages."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile

VERSION = "0.1.0"


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(path))


def digest_file(path: Path) -> dict:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or is_link(path):
        raise OSError("not a regular file")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise OSError("file replaced before hashing")
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
    final = path.lstat()
    # Windows lstat and fstat can expose different ctime semantics. Compare ctime
    # only between two observations made through the same interface.
    fingerprint = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if (fingerprint(before) != fingerprint(opened) or fingerprint(opened) != fingerprint(after)
            or fingerprint(after) != fingerprint(final) or before.st_ctime_ns != final.st_ctime_ns
            or opened.st_ctime_ns != after.st_ctime_ns or is_link(path)):
        raise OSError("file changed while hashing; retry on a stable directory")
    return {"sha256": digest, "size": after.st_size}


def snapshot(root: Path, excludes: list[str] | None = None) -> dict:
    if is_link(root):
        raise ValueError("the root must not be a symlink or junction")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("the root must be a directory")
    patterns = sorted(set(excludes or []))
    files: dict[str, dict] = {}
    skipped: list[str] = []
    errors: list[str] = []

    def excluded(relative: str) -> bool:
        return any(fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(relative + "/", pattern) for pattern in patterns)

    def walk_error(error: OSError) -> None:
        errors.append(str(error))

    for current, directories, names in os.walk(root, topdown=True, followlinks=False, onerror=walk_error):
        parent = Path(current)
        keep = []
        for name in sorted(directories):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if excluded(relative):
                continue
            if is_link(path):
                skipped.append(relative)
            else:
                keep.append(name)
        directories[:] = keep
        for name in sorted(names):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if excluded(relative):
                continue
            try:
                if is_link(path) or not stat.S_ISREG(path.lstat().st_mode):
                    skipped.append(relative)
                    continue
                files[relative] = digest_file(path)
            except OSError as error:
                errors.append(f"{relative}: {error}")
    if errors:
        raise ValueError("Snapshot incomplete; no baseline written:\n" + "\n".join(errors))
    return {"schema_version": 1, "algorithm": "sha256", "created_at": datetime.now(timezone.utc).isoformat(), "excludes": patterns, "skipped": sorted(skipped), "files": dict(sorted(files.items()))}


def validate_manifest(value: object) -> dict:
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1 or value.get("algorithm") != "sha256":
        raise ValueError("Unsupported snapshot format; expected schema_version 1 and sha256")
    if not isinstance(value.get("excludes"), list) or not all(isinstance(pattern, str) for pattern in value["excludes"]):
        raise ValueError("Invalid snapshot exclusion patterns")
    if not isinstance(value.get("files"), dict):
        raise ValueError("Invalid snapshot file table")
    for name, record in value["files"].items():
        if not isinstance(name, str) or not name or "\\" in name or ":" in name or name.startswith("/") or any(part in {"", ".", ".."} for part in name.split("/")) or PurePosixPath(name).is_absolute():
            raise ValueError("Snapshot contains an invalid relative path")
        if not isinstance(record, dict) or type(record.get("size")) is not int or record["size"] < 0:
            raise ValueError("Snapshot contains an invalid file size")
        digest = record.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("Snapshot contains an invalid SHA-256 digest")
    return value


def load_manifest(path: Path) -> dict:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key in snapshot")
            result[key] = value
        return result
    return validate_manifest(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys))


def compare(before: dict, after: dict) -> dict:
    validate_manifest(before)
    validate_manifest(after)
    if sorted(set(before["excludes"])) != sorted(set(after["excludes"])):
        raise ValueError("Snapshots use different exclusions; use the same scan scope")
    old, new = before["files"], after["files"]
    return {"added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()), "changed": sorted(name for name in old.keys() & new.keys() if old[name] != new[name]), "unchanged": sum(old[name] == new[name] for name in old.keys() & new.keys())}


def save_manifest(path: Path, value: dict) -> None:
    # Atomic replacement prevents an interrupted write from corrupting a baseline.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, prefix=".filesentinel-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create and compare SHA-256 file-integrity snapshots.")
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("snapshot", help="Hash the regular files in a directory")
    scan.add_argument("root", type=Path)
    scan.add_argument("-o", "--output", type=Path, required=True)
    scan.add_argument("--exclude", action="append", default=[], help="Case-sensitive glob against a relative POSIX path; repeatable")
    diff = commands.add_parser("compare", help="Compare two JSON snapshots")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    diff.add_argument("--json", action="store_true", help="Write a machine-readable report")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            output = args.output.resolve()
            root = args.root.resolve(strict=True)
            if output.is_relative_to(root):
                raise ValueError("Store snapshots outside the scanned directory to keep scan scopes identical")
            manifest = snapshot(args.root, args.exclude)
            save_manifest(output, manifest)
            print(f"Saved {len(manifest['files'])} files; skipped {len(manifest['skipped'])} links or special files.")
            return 0
        report = compare(load_manifest(args.before), load_manifest(args.after))
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for category in ("added", "removed", "changed"):
                print(f"{category.capitalize()}: {len(report[category])}")
                for name in report[category]:
                    print(f"  {name}")
            print(f"Unchanged: {report['unchanged']}")
        return int(any(report[key] for key in ("added", "removed", "changed")))
    except (OSError, ValueError, UnicodeError) as error:
        print(f"FileSentinel: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
