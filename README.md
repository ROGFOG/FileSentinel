# FileSentinel

What changed in a directory between two runs? FileSentinel records relative paths,
sizes and SHA-256 hashes, then lists added, removed and changed files. It is a
single Python 3.12+ script using only the standard library.

## Quick start

Keep both snapshots **outside** the directory you scan:

```sh
python filesentinel.py snapshot ./documents -o before.json --exclude '*.tmp'
# Edit documents, then repeat with the same exclusions.
python filesentinel.py snapshot ./documents -o after.json --exclude '*.tmp'
python filesentinel.py compare before.json after.json
python filesentinel.py compare before.json after.json --json
```

On Windows, `py -3` can replace `python`. Quote paths containing spaces.

A repeatable example in [docs/example.md](docs/example.md) changes a checklist,
adds a note and removes an old file. Its actual CLI output is:

```text
Added: 1
  notes/new.txt
Removed: 1
  notes/old.txt
Changed: 1
  notes/checklist.txt
Unchanged: 1
```

`compare` returns **0** for identical snapshots, **1** for differences and **2** for
an input or filesystem error. `snapshot` returns 0 when it saves successfully.
`--version` prints the version.

## What goes into a snapshot

JSON schema version 1 stores the algorithm, UTC creation time, effective exclusion
patterns, skipped paths and a sorted file table. Paths use `/` and are relative
to the scanned directory. The absolute source path is omitted.

`--exclude` matches case-sensitive globs against the full relative path. Repeat
it for multiple patterns; `cache/**` excludes a directory tree. Comparing different
exclusion sets is an error because those snapshots cover different files.

Links, junctions and special files are listed as skipped. A read or traversal error
stops the snapshot. Checks around each read catch files replaced or changed during
hashing; the final JSON replaces its destination atomically.

## Known issues

A scan reads files in sequence, so use a stable directory. It records content and
paths; ACLs, ownership and alternate data streams are outside the format. Keep the
baseline separately protected because snapshots are unsigned. Review filenames
before sharing a report.

## Checking changes

```sh
python -m unittest -v
```

Checked on Windows with Python 3.12.14: 10 tests. The real symlink case skips when
the OS denies link creation. CI covers Windows and Linux: junction handling and
file identity checks depend on the OS. Python 3.12 checks the minimum version;
3.13 checks compatibility with the next supported version.

[Заметки о формате и чтении файлов](docs/design.ru.md) explain the comparison and
the Windows ctime detail. Distributed under [MIT](LICENSE).
