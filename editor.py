“””
editor.py — Apply insert/remove operations to files, with backup.
“””

import shutil
from pathlib import Path
from datetime import datetime

def *backup(filepath: Path) -> Path:
ts = datetime.now().strftime(”%Y%m%d*%H%M%S”)
backup = filepath.with_suffix(filepath.suffix + f”.bak_{ts}”)
shutil.copy2(filepath, backup)
return backup

def apply_insert(
filepath: Path,
insert_at: int,      # 1-based line number to insert BEFORE
lines: list[str],
backup: bool = True,
) -> Path | None:
“”“Insert lines into file before line insert_at. Returns backup path or None.”””
file_lines = filepath.read_text(encoding=“utf-8”, errors=“replace”).splitlines(keepends=True)

```
# Ensure lines end with newline
new_lines = []
for ln in lines:
    new_lines.append(ln if ln.endswith("\n") else ln + "\n")

idx = max(0, min(insert_at - 1, len(file_lines)))
file_lines[idx:idx] = new_lines

bak = _backup(filepath) if backup else None
filepath.write_text("".join(file_lines), encoding="utf-8")
return bak
```

def apply_remove(
filepath: Path,
line_start: int,     # 1-based inclusive
line_end: int,       # 1-based inclusive
backup: bool = True,
) -> Path | None:
“”“Remove lines line_start..line_end (inclusive) from file.”””
file_lines = filepath.read_text(encoding=“utf-8”, errors=“replace”).splitlines(keepends=True)

```
start_idx = max(0, line_start - 1)
end_idx = min(len(file_lines), line_end)

del file_lines[start_idx:end_idx]

bak = _backup(filepath) if backup else None
filepath.write_text("".join(file_lines), encoding="utf-8")
return bak
```