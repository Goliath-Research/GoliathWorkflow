#!/usr/bin/env bash
# Rsync /work/<disease>/ to /work/projects/<disease>/ (copy-then-archive).
set -euo pipefail

OLD_ROOT="/work/prostate-cancer"
NEW_ROOT="/work/projects/prostate-cancer"
SITE_DIR="/work/site"
DRY_RUN=0
SYMLINK=0
DATE_TAG="$(date -u +%Y%m%dT%H%M%SZ)"

usage() {
  echo "Usage: $0 [--old-root PATH] [--new-root PATH] [--site-dir PATH] [--dry-run] [--symlink]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old-root) OLD_ROOT="$2"; shift 2 ;;
    --new-root) NEW_ROOT="$2"; shift 2 ;;
    --site-dir) SITE_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --symlink) SYMLINK=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1"; usage ;;
  esac
done

if [[ ! -d "$OLD_ROOT" ]]; then
  echo "source missing: $OLD_ROOT" >&2
  exit 1
fi

echo "old_root=$OLD_ROOT new_root=$NEW_ROOT dry_run=$DRY_RUN"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "would mkdir -p $NEW_ROOT $SITE_DIR"
  for child in "$OLD_ROOT"/*; do
    base="$(basename "$child")"
    [[ "$base" == "samples" ]] && continue
    echo "would rsync -a $child/ $NEW_ROOT/$base/"
  done
  echo "would archive $OLD_ROOT -> ${OLD_ROOT}.migrated.${DATE_TAG}"
  [[ "$SYMLINK" -eq 1 ]] && echo "would ln -sfn $NEW_ROOT $OLD_ROOT"
  exit 0
fi

mkdir -p "$NEW_ROOT" "$SITE_DIR"

for child in "$OLD_ROOT"/*; do
  [[ -e "$child" ]] || continue
  base="$(basename "$child")"
  if [[ "$base" == "samples" ]]; then
    echo "skip samples subtree: $child"
    continue
  fi
  echo "rsync $child -> $NEW_ROOT/$base/"
  rsync -a "$child/" "$NEW_ROOT/$base/"
done

if [[ -d "$NEW_ROOT/configs" ]]; then
  echo "spot-check configs:"
  ls -la "$NEW_ROOT/configs" | head -5
fi

ARCHIVE="${OLD_ROOT}.migrated.${DATE_TAG}"
if [[ -e "$ARCHIVE" ]]; then
  echo "archive already exists: $ARCHIVE" >&2
  exit 1
fi

mv "$OLD_ROOT" "$ARCHIVE"
echo "archived source to $ARCHIVE"

if [[ "$SYMLINK" -eq 1 ]]; then
  ln -sfn "$NEW_ROOT" "$OLD_ROOT"
  echo "symlink $OLD_ROOT -> $NEW_ROOT"
fi

echo "filesystem migration complete"
