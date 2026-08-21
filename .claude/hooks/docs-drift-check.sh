#!/usr/bin/env bash
# Stop hook: advisory reminder when code changed but no docs did.
#
# Fires at the end of a turn. Never blocks — it prints a note and exits 0.
# Rationale and the loop it guards: .claude/skills/docs-sync/SKILL.md
set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# Last field handles renames ("R  old -> new") by taking the destination path.
changed=$(git status --porcelain 2>/dev/null | awk '{print $NF}')
[ -n "$changed" ] || exit 0

code=$(printf '%s\n' "$changed" | grep -E '^(apps|packages)/' || true)
docs=$(printf '%s\n' "$changed" | grep -E '^docs/' || true)

if [ -n "$code" ] && [ -z "$docs" ]; then
  printf '%s' '{"systemMessage":"Code changed under apps/ or packages/ but no docs changed. Update the affected docs before committing (docs-sync skill), or confirm nothing documented was affected."}'
fi

exit 0
