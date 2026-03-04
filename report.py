# report.py — Parse freeform report files into structured change objects.

# 

# Handles inconsistent formatting:

# - (Added lines 33-39) / Added lines 33-39

# - (Removed lines 25-30) / Removed lines 3-6 / Remove lines / removed lines

import re
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Change:
action: str          # ‘insert’ or ‘remove’
line_start: int      # 1-based hint from report
line_end: int        # 1-based hint from report
lines: list[str] = field(default_factory=list)

```
def __str__(self):
    verb = "INSERT" if self.action == "insert" else "REMOVE"
    return f"{verb} lines {self.line_start}-{self.line_end} ({len(self.lines)} lines)"
```

@dataclass
class FileChange:
filepath: str
changes: list[Change] = field(default_factory=list)

```
def __str__(self):
    return f"{self.filepath} ({len(self.changes)} change(s))"
```

# Matches action headers in various forms:

# (Added lines 33-39) / Added lines 33-39

# (Removed lines 25-30) / Removed lines 3-6

# Remove the line   <- no line numbers, treat as best-effort

ACTION_RE = re.compile(
r”””
(?                         # optional opening paren
(added|removed?|inserted?)  # verb
\s+
(?:lines?\s+)?              # optional “lines” word
(\d+)                       # start line
(?:\s*[-–]\s*(\d+))?        # optional -end line
)?                         # optional closing paren
“””,
re.IGNORECASE | re.VERBOSE,
)

# Loose filepath: starts with / or ./

FILEPATH_RE = re.compile(r”^(/[\w./-]+|.?/[\w./-]+)$”)

def _is_filepath(line: str) -> bool:
stripped = line.strip()
return bool(FILEPATH_RE.match(stripped)) and not stripped.startswith(”#”)

# Return (action, start, end) if line is an action header, else None

def _parse_action(line: str) -> tuple[str, int, int] | None:
m = ACTION_RE.search(line.strip())
if not m:
return None
verb = m.group(1).lower()
action = “insert” if verb.startswith(“add”) or verb.startswith(“ins”) else “remove”
start = int(m.group(2))
end = int(m.group(3)) if m.group(3) else start
return action, start, end

# Parse a freeform report file, return list of FileChange objects

def parse_report(report_path: str | Path) -> list[FileChange]:
text = Path(report_path).read_text(encoding=“utf-8”, errors=“replace”)
lines = text.splitlines()

```
file_changes: list[FileChange] = []
current_file: FileChange | None = None
current_change: Change | None = None

def _flush_change():
    nonlocal current_change
    if current_change and current_file:
        current_file.changes.append(current_change)
    current_change = None

def _flush_file():
    nonlocal current_file
    _flush_change()
    if current_file:
        file_changes.append(current_file)
    current_file = None

for raw in lines:
    line = raw.rstrip()

    # Blank lines: separator between sections, don't consume as code
    if not line.strip():
        continue

    # Check for a new filepath
    if _is_filepath(line):
        _flush_file()
        current_file = FileChange(filepath=line.strip())
        continue

    if current_file is None:
        # Haven't hit a filepath yet — skip
        continue

    # Check for an action header
    parsed = _parse_action(line)
    if parsed:
        _flush_change()
        action, start, end = parsed
        current_change = Change(action=action, line_start=start, line_end=end)
        continue

    # Otherwise it's a content line for the current change
    if current_change is not None:
        current_change.lines.append(raw)  # preserve original indentation

_flush_file()
return file_changes
```