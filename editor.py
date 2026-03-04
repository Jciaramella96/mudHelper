# editor.py — Apply insert/remove operations to files, with backup.

import shutil
from pathlib import Path
from datetime import datetime

def *backup(filepath: Path) -> Path:
ts = datetime.now().strftime(”%Y%m%d*%H%M%S”)
backup = filepath.with_suffix(filepath.suffix + f”.bak_{ts}”)
shutil.copy2(filepath, backup)
return backup

# Insert lines into file before line insert_at (1-based). Returns backup path or None.

def apply_insert(
filepath: Path,
insert_at: int,
lines: list[str],
backup: bool = True,
) -> Path | None:
file_lines = filepath.read_text(encoding=“utf-8”, errors=“replace”).splitlines(keepends=True)

```
# Ensure each line ends with a newline
new_lines = [ln if ln.endswith("\n") else ln + "\n" for ln in lines]

idx = max(0, min(insert_at - 1, len(file_lines)))
file_lines[idx:idx] = new_lines

bak = _backup(filepath) if backup else None
filepath.write_text("".join(file_lines), encoding="utf-8")
return bak
```

# Remove lines line_start..line_end inclusive (1-based). Returns backup path or None.

def apply_remove(
filepath: Path,
line_start: int,
line_end: int,
backup: bool = True,
) -> Path | None:
file_lines = filepath.read_text(encoding=“utf-8”, errors=“replace”).splitlines(keepends=True)

```
start_idx = max(0, line_start - 1)
end_idx = min(len(file_lines), line_end)
del file_lines[start_idx:end_idx]

bak = _backup(filepath) if backup else None
filepath.write_text("".join(file_lines), encoding="utf-8")
return bak
```