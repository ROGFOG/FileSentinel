# FileSentinel

Save file hashes for a directory, then compare two snapshots to list added,
removed and changed files. Snapshots use SHA-256 and relative paths.

Python 3.12+. Standard library only. [Design notes, RU](docs/design.ru.md).

## Quick start

Keep the snapshot files **outside** the scanned directory:

```sh
python filesentinel.py snapshot ./documents -o before.json --exclude '*.tmp'
# Make changes to documents, then use the same exclusion patterns.
python filesentinel.py snapshot ./documents -o after.json --exclude '*.tmp'
python filesentinel.py compare before.json after.json
python filesentinel.py compare before.json after.json --json
```

On Windows, replace `python` with `py -3` if that is your installed launcher.
Paths containing spaces should be quoted.

```text
Added: 1
  notes/new.txt
Removed: 0
Changed: 1
  notes/checklist.txt
Unchanged: 12
```

Exit codes: **0** success/no differences, **1** differences found by compare,
**2** input or filesystem error. `--version` prints the application version.

## Snapshot contract

JSON contains schema_version 1, algorithm sha256, UTC creation time, exclusion
patterns, skipped paths, and a sorted mapping from relative POSIX paths to file
size and lowercase SHA-256. Absolute source paths are not stored.

Exclusions use case-sensitive glob matching against the full relative path.
Repeat `--exclude` for multiple patterns; `cache/**` excludes a directory tree.
Compare refuses snapshots with different exclusion patterns.

Links, junctions and special files are skipped and listed. A read or traversal
error prevents saving a partial baseline. Files replaced or modified during
hashing cause an error; snapshot writes use atomic replacement.

## Limits and trust

This compares file contents and paths, not ACLs, alternate data streams, ownership
or malware behavior. Snapshots are not signed: protect the baseline separately.
Use a stable directory, not one under concurrent or hostile modification. Per-file
checks are not an atomic filesystem snapshot, and this is not a privileged scanner.
Reports and snapshots disclose filenames; inspect them before sharing.

## Tests

```sh
python -m unittest -v
```

CI runs on Linux and Windows with Python 3.12 and 3.13. Symlink tests skip on
hosts that do not permit creating symlinks.

See [open tasks](https://github.com/ROGFOG/FileSentinel/issues) for the next steps.

MIT license.
