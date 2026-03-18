#!/usr/bin/env bash
# clean_dooku.sh — Strip a junk directory from Dooku.zip and repack cleanly
# Usage: ./clean_dooku.sh <path/to/Dooku.zip> <junk_dir_name_inside_zip>
# Example: ./clean_dooku.sh /backups/Dooku.zip trash_dir

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
SAFETY_BUFFER_MB=512   # Extra headroom required beyond raw uncompressed size
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GRN}[INFO]${NC}  $*"; }
warn() { echo -e "${YLW}[WARN]${NC}  $*"; }
die()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Argument validation ───────────────────────────────────────────────────────
[[ $# -ne 2 ]] && die "Usage: $0 <zipfile> <junk_directory_name>"

ZIP_PATH="$(realpath "$1")"
JUNK_DIR="$2"

[[ -f "$ZIP_PATH" ]] || die "Zip file not found: $ZIP_PATH"
command -v unzip &>/dev/null || die "'unzip' not installed"
command -v zip   &>/dev/null || die "'zip' not installed"

# ── Precheck: verify zip integrity ───────────────────────────────────────────
precheck_zip_integrity() {
    log "Testing zip integrity..."
    unzip -t "$ZIP_PATH" &>/dev/null || die "Zip integrity test failed. Aborting."
    log "Zip integrity OK."
}

# ── Precheck: disk space ──────────────────────────────────────────────────────
# Strategy:
#   - Get uncompressed size of zip contents via 'unzip -l'
#   - Get available KB on the partition where we'll be working (same as zip location)
#   - Require: available_space > uncompressed_size + SAFETY_BUFFER
#     The buffer covers the rezip phase where both the extracted tree
#     and the new zip file coexist temporarily on disk.
precheck_disk_space() {
    local zip_dir
    zip_dir="$(dirname "$ZIP_PATH")"

    # unzip -l last line: "  <total_bytes>  <N> files"
    local uncompressed_bytes
    uncompressed_bytes=$(unzip -l "$ZIP_PATH" \
        | awk 'END { print $1 }')

    # Sanity check — should be a number
    [[ "$uncompressed_bytes" =~ ^[0-9]+$ ]] \
        || die "Could not parse uncompressed size from zip listing. Got: '$uncompressed_bytes'"

    local uncompressed_mb=$(( uncompressed_bytes / 1024 / 1024 ))
    local required_mb=$(( uncompressed_mb + SAFETY_BUFFER_MB ))

    # df -Pk: POSIX output, 1K blocks — column 4 is available KB
    local available_kb
    available_kb=$(df -Pk "$zip_dir" | awk 'NR==2 { print $4 }')
    local available_mb=$(( available_kb / 1024 ))

    log "Uncompressed size : ~${uncompressed_mb} MB"
    log "Safety buffer     :  ${SAFETY_BUFFER_MB} MB"
    log "Required free     : ~${required_mb} MB"
    log "Available on part.:  ${available_mb} MB  (partition: $(df -Pk "$zip_dir" | awk 'NR==2{print $1}'))"

    if (( available_mb < required_mb )); then
        die "Insufficient disk space. Need ~${required_mb} MB, only ${available_mb} MB free. Aborting."
    fi

    log "Disk space check passed."
}

# ── Precheck: junk dir actually exists in the zip ────────────────────────────
precheck_junk_dir_exists() {
    log "Checking '${JUNK_DIR}' exists inside zip..."
    unzip -l "$ZIP_PATH" | grep -q "/${JUNK_DIR}/" \
        || unzip -l "$ZIP_PATH" | grep -q " ${JUNK_DIR}/" \
        || die "Directory '${JUNK_DIR}' not found inside zip. Check the name and try again."
    log "Found '${JUNK_DIR}' in zip."
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    log "=== Starting Dooku zip cleanup ==="
    log "Target zip : $ZIP_PATH"
    log "Junk dir   : $JUNK_DIR"

    # Run all prechecks — any failure exits via die()
    precheck_zip_integrity
    precheck_disk_space
    precheck_junk_dir_exists

    # Create a temp working directory on the same partition
    local work_dir
    work_dir="$(dirname "$ZIP_PATH")/.dooku_work_$$"
    mkdir -p "$work_dir"
    log "Work dir   : $work_dir"

    # Trap: clean up work dir on any unexpected exit
    trap 'warn "Interrupted — cleaning up work dir..."; rm -rf "$work_dir"' EXIT

    # 1. Extract
    log "Extracting zip..."
    unzip -q "$ZIP_PATH" -d "$work_dir"

    # 2. Delete junk directory
    local junk_path
    # Handle both top-level and nested junk dir
    junk_path=$(find "$work_dir" -maxdepth 3 -type d -name "$JUNK_DIR" | head -1)
    [[ -n "$junk_path" ]] || die "Could not locate '$JUNK_DIR' in extracted tree."
    log "Deleting junk dir: $junk_path"
    rm -rf "$junk_path"

    # 3. Rezip — use pushd/popd for clean relative paths inside the archive
    local new_zip="${ZIP_PATH%.zip}_cleaned.zip"
    log "Repacking to: $new_zip"
    pushd "$work_dir" > /dev/null
    zip -qr "$new_zip" .
    popd > /dev/null

    # 4. Verify new zip
    log "Verifying new zip..."
    unzip -t "$new_zip" &>/dev/null || die "New zip failed integrity check! Original untouched."

    # 5. Replace original zip
    log "Replacing original zip..."
    mv "$new_zip" "$ZIP_PATH"

    # 6. Disarm trap and clean up work dir
    trap - EXIT
    rm -rf "$work_dir"

    log "=== Done. Cleaned zip: $ZIP_PATH ==="
}

main
