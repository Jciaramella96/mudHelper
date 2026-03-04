# report.py - Parse freeform report files into structured change objects.

# 

# Handles inconsistent formatting:

# 

# - Added (lines 33-39) / Removed (lines 25-30)

# - Added lines 376-394 / Removed lines 3-6 / Inserted line 42

# - Parentheses around ranges: (3-6), lines (6-6), (lines 11-17)

# - File headers like “path/to/file:” and “Only in New: path/to/file”

# - Preserves blank lines inside change content

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
def __str__(self) -> str:
    verb = "INSERT" if self.action == "insert" else "REMOVE"
    return f"{verb} lines {self.line_start}-{self.line_end} ({len(self.lines)} lines)"
```

@dataclass
class FileChange:
filepath: str
changes: list[Change] = field(default_factory=list)
only_in_new: bool = False  # True if the report line was “Only in New: <path>”

```
def __str__(self) -> str:
    flag = " (only in new)" if self.only_in_new else ""
    return f"{self.filepath}{flag} ({len(self.changes)} change(s))"
```

# Matches action headers in various forms:

# Added (lines 376-394)

# Removed (lines 6-7)

# Removed lines (6-6)

# Added lines 376-394

# Removed lines 3-6

# Inserted line 42

ACTION_RE = re.compile(
r”””
^\s*
(?P<verb>added|removed?|inserted?)      # verb
\b
(?:\s*(\s*lines?\s*)|\s+lines?)?      # optional “(lines)” or “lines”/“line”
\s*
(?                                     # optional opening “(” before numbers
(?P<start>\d+)                          # start line
(?:\s*[-]\s*(?P<end>\d+))?              # optional end line
)?                                     # optional closing “)”
\s*:?                                   # optional trailing colon
\s*$
“””,
re.IGNORECASE | re.VERBOSE,
)

# File header: “path/to/file.ext:” (supports absolute “/”, “./”, “../”, and bare relative)

FILE_HEADER_RE = re.compile(r’^\s*([\w./-]+):\s*$’)

# “Only in New: path/to/file”

ONLY_IN_NEW_RE = re.compile(r’^\s*Only in New:\s+([\w./-]+)\s*$’)

def _parse_action(line: str) -> tuple[str, int, int] | None:
# Return (action, start, end) if the line is an action header; otherwise None.
m = ACTION_RE.match(line.strip())
if not m:
return None

```
verb = m.group("verb").lower()
action = "insert" if verb.startswith(("add", "ins")) else "remove"

start = int(m.group("start"))
end_g = m.group("end")
end = int(end_g) if end_g is not None else start

return action, start, end
```

def parse_report(report_path: str | Path) -> list[FileChange]:
# Parse a text report of file changes into a list of FileChange objects.
text = Path(report_path).read_text(encoding=“utf-8”, errors=“replace”)
lines = text.splitlines()

```
file_changes: list[FileChange] = []
current_file: FileChange | None = None
current_change: Change | None = None

def _trim_trailing_blanks() -> None:
    nonlocal current_change
    if current_change:
        while current_change.lines and not current_change.lines[-1].strip():
            current_change.lines.pop()

def _flush_change() -> None:
    nonlocal current_change
    if current_change and current_file:
        _trim_trailing_blanks()
        current_file.changes.append(current_change)
    current_change = None

def _flush_file() -> None:
    nonlocal current_file
    _flush_change()
    if current_file:
        file_changes.append(current_file)
    current_file = None

for raw in lines:
    line = raw.rstrip()

    # Preserve blank lines inside a change; otherwise treat as separators
    if not line.strip():
        if current_change is not None:
            current_change.lines.append(raw)
        continue

    # File header: "path/to/file.ext:"
    m_file = FILE_HEADER_RE.match(line)
    if m_file:
        _flush_file()
        current_file = FileChange(filepath=m_file.group(1))
        continue

    # "Only in New: path/to/file"
    m_only_new = ONLY_IN_NEW_RE.match(line)
    if m_only_new:
        _flush_file()
        file_changes.append(
            FileChange(filepath=m_only_new.group(1), only_in_new=True)
        )
        continue

    if current_file is None:
        continue

    # Action header (Added/Removed/Inserted ...)
    parsed = _parse_action(line)
    if parsed:
        _flush_change()
        action, start, end = parsed
        current_change = Change(action=action, line_start=start, line_end=end)
        continue

    # Otherwise it's a content line for the current change
    if current_change is not None:
        current_change.lines.append(raw)

_flush_file()
return file_changes
```

if **name** == “**main**”:
import sys

```
if len(sys.argv) != 2:
    print("Usage: python report.py <report.txt>")
    sys.exit(1)

result = parse_report(sys.argv[1])
for fc in result:
    print(fc)
    for ch in fc.changes:
        print("  ", ch)
        if ch.lines:
            print("    --- content ---")
            for ln in ch.lines:
                print("    " + ln)
            print("    ---------------")
```