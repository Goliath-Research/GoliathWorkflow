#!/usr/bin/env bash
# Deprecated wrapper — use scripts/build_mojo_align_image.sh
echo "warning: build_methylgrapher_mojo_image.sh is deprecated; use build_mojo_align_image.sh" >&2
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/build_mojo_align_image.sh" "$@"
