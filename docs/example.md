# A small directory comparison

Run from the repository root with Python 3.12+. This creates a new temporary
folder and prints a real comparison; snapshot files stay outside documents.

```python
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory() as temporary:
    base = Path(temporary)
    documents = base / "documents"
    notes = documents / "notes"
    notes.mkdir(parents=True)
    for name, text in {"checklist.txt": "before", "old.txt": "old", "keep.txt": "keep"}.items():
        (notes / name).write_text(text, encoding="utf-8")
    cli = [sys.executable, "filesentinel.py"]
    subprocess.run([*cli, "snapshot", str(documents), "-o", str(base / "before.json")], check=True)
    (notes / "checklist.txt").write_text("after", encoding="utf-8")
    (notes / "old.txt").unlink()
    (notes / "new.txt").write_text("new", encoding="utf-8")
    subprocess.run([*cli, "snapshot", str(documents), "-o", str(base / "after.json")], check=True)
    result = subprocess.run([*cli, "compare", str(base / "before.json"), str(base / "after.json")])
    assert result.returncode == 1
```

Checked on Windows with Python 3.12.14:

```text
Saved 3 files; skipped 0 links or special files.
Saved 3 files; skipped 0 links or special files.
Added: 1
  notes/new.txt
Removed: 1
  notes/old.txt
Changed: 1
  notes/checklist.txt
Unchanged: 1
```

Exit code 1 records the differences shown above. The example contains generated
fixture files; it scans no personal folders.
