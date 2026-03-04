# finder.py - Search a directory tree for files listed in the report.

# 

# Strategy for each file:

# 1. Try the exact path (absolute or relative to search_root)

# 2. Strip leading / and try under search_root

# 3. Match last N path components (3, then 2, then 1)

# 4. Give up -> None

from pathlib import Path

# For each FileChange, locate the actual file under search_root.

# Returns dict mapping report filepath string -> resolved Path (or None if not found)

def find_files(file_changes, search_root: str | Path) -> dict[str, Path | None]:
root = Path(search_root)
results: dict[str, Path | None] = {}

```
# Pre-build index of all files under root for efficient lookup
all_files: list[Path] = [f for f in root.rglob("*") if f.is_file()]

for fc in file_changes:
    report_path = Path(fc.filepath)
    results[fc.filepath] = _resolve(report_path, root, all_files)

return results
```

def _resolve(report_path: Path, root: Path, all_files: list[Path]) -> Path | None:
# 1. Exact absolute path
if report_path.is_absolute() and report_path.exists():
return report_path

```
# 2. Relative to search root
candidate = root / report_path
if candidate.exists():
    return candidate

# 3. Strip leading / and try under root
relative = Path(*report_path.parts[1:]) if report_path.is_absolute() else report_path
candidate2 = root / relative
if candidate2.exists():
    return candidate2

# 4. Match last N components against all files (try 3, then 2, then 1)
parts = report_path.parts
for n in (3, 2, 1):
    if len(parts) >= n:
        suffix = Path(*parts[-n:])
        matches = [f for f in all_files if f.parts[-n:] == suffix.parts]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            # Prefer shortest path (least nested)
            return sorted(matches, key=lambda p: len(p.parts))[0]

return None
```