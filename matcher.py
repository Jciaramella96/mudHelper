“””
matcher.py — Fuzzy/pattern matching to locate code blocks in files.

Given a Change (with hint line numbers and content lines), find the best
actual location in the file, even if whitespace or comments have shifted.
“””

import re
from difflib import SequenceMatcher
from dataclasses import dataclass

@dataclass
class MatchResult:
found: bool
line_start: int      # 1-based, actual location in file
line_end: int        # 1-based, inclusive
confidence: float    # 0.0 – 1.0
method: str          # ‘exact’, ‘hint’, ‘fuzzy’, ‘pattern’

def _normalize(line: str) -> str:
“”“Strip leading/trailing whitespace and collapse internal whitespace.”””
return re.sub(r”\s+”, “ “, line.strip())

def _similarity(a: str, b: str) -> float:
return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()

def _block_similarity(file_lines: list[str], start_idx: int, change_lines: list[str]) -> float:
“”“Score how well change_lines matches file_lines starting at start_idx (0-based).”””
end_idx = start_idx + len(change_lines)
if end_idx > len(file_lines):
return 0.0
scores = [
_similarity(file_lines[start_idx + i], change_lines[i])
for i in range(len(change_lines))
]
return sum(scores) / len(scores) if scores else 0.0

def find_block(
file_lines: list[str],
change_lines: list[str],
hint_start: int,      # 1-based
hint_end: int,        # 1-based
search_window: int = 40,
confidence_threshold: float = 0.6,
) -> MatchResult:
“””
Find where change_lines lives in file_lines.

```
Steps:
1. Try exact match at hint location
2. Try exact match scanning whole file
3. Try fuzzy match within hint ± search_window
4. Try fuzzy match whole file
"""
if not change_lines:
    # No content to match — trust the hint
    return MatchResult(
        found=True,
        line_start=hint_start,
        line_end=hint_end,
        confidence=1.0,
        method="hint",
    )

n = len(file_lines)
hint_idx = hint_start - 1  # convert to 0-based

# --- 1. Exact match at hint ---
if hint_idx >= 0 and hint_idx + len(change_lines) <= n:
    score = _block_similarity(file_lines, hint_idx, change_lines)
    if score >= 0.95:
        return MatchResult(
            found=True,
            line_start=hint_start,
            line_end=hint_start + len(change_lines) - 1,
            confidence=score,
            method="exact",
        )

# --- 2. Exact scan whole file ---
best_idx = -1
best_score = 0.0
for i in range(n - len(change_lines) + 1):
    score = _block_similarity(file_lines, i, change_lines)
    if score > best_score:
        best_score = score
        best_idx = i

if best_score >= 0.95:
    return MatchResult(
        found=True,
        line_start=best_idx + 1,
        line_end=best_idx + len(change_lines),
        confidence=best_score,
        method="exact",
    )

# --- 3. Fuzzy within window ---
window_start = max(0, hint_idx - search_window)
window_end = min(n - len(change_lines) + 1, hint_idx + search_window)
best_window_idx = -1
best_window_score = 0.0
for i in range(window_start, window_end):
    score = _block_similarity(file_lines, i, change_lines)
    if score > best_window_score:
        best_window_score = score
        best_window_idx = i

if best_window_score >= confidence_threshold:
    return MatchResult(
        found=True,
        line_start=best_window_idx + 1,
        line_end=best_window_idx + len(change_lines),
        confidence=best_window_score,
        method="fuzzy",
    )

# --- 4. Best match anywhere ---
if best_score >= confidence_threshold:
    return MatchResult(
        found=True,
        line_start=best_idx + 1,
        line_end=best_idx + len(change_lines),
        confidence=best_score,
        method="fuzzy",
    )

# Not found with enough confidence
return MatchResult(
    found=False,
    line_start=hint_start,
    line_end=hint_end,
    confidence=best_score,
    method="none",
)
```

def find_insert_line(
file_lines: list[str],
hint_start: int,
search_window: int = 20,
) -> int:
“””
Find the best line to insert at, starting from hint_start.
If the hint line is ‘free’ (empty or only whitespace), use it.
Otherwise scan downward for the next empty/whitespace line.
Returns 1-based line number.
“””
n = len(file_lines)
idx = hint_start - 1  # 0-based

```
# Clamp
idx = max(0, min(idx, n))

# Check if hint line is empty
if idx < n and not file_lines[idx].strip():
    return idx + 1

# Scan downward
for offset in range(1, search_window + 1):
    check = idx + offset
    if check >= n:
        break
    if not file_lines[check].strip():
        return check + 1

# Fall back to hint (insert after occupied line)
return min(hint_start, n + 1)
```