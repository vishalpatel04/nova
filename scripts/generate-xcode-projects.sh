#!/usr/bin/env bash
# Generate Xcode projects from project.yml (requires xcodegen: brew install xcodegen)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

generate() {
    local dir="$1"
    if command -v xcodegen >/dev/null 2>&1; then
        (cd "$dir" && xcodegen generate)
        echo "Generated Xcode project in $dir"
    else
        echo "xcodegen not installed — using pre-generated project or install with: brew install xcodegen"
        exit 1
    fi
}

generate "$ROOT/apps/ios"
generate "$ROOT/apps/macos"
