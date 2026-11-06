#!/usr/bin/env bash
# sync.sh — install or update the factory kit in a problem repo.
# Usage: ./sync.sh <problem-repo-dir>
#
# Always overwrites the engine: factory.sh, doctor.sh, lib/, dashboard/.
# Adds a default prompt only where the repo has none. Never touches what the repo owns:
# gates/, AGENTS.md, factory.conf, and any prompt it already has.
# Refuses a target with uncommitted changes, so every sync is one reviewable diff.
set -euo pipefail

KIT="$(cd "$(dirname "$0")/kit" && pwd)"
target="${1:?usage: ./sync.sh <problem-repo-dir>}"

git -C "$target" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "sync: $target is not a git repo" >&2; exit 1; }
[[ -z "$(git -C "$target" status --porcelain)" ]] \
  || { echo "sync: $target has uncommitted changes: commit or stash them first" >&2; exit 1; }

changed=()
copy() {  # copy <path relative to kit/>, recording it when the target's copy differs
  local rel="$1"
  if ! cmp -s "$KIT/$rel" "$target/$rel"; then
    mkdir -p "$(dirname "$target/$rel")"
    cp "$KIT/$rel" "$target/$rel"
    changed+=("$rel")
  fi
}

copy factory.sh
copy doctor.sh
for f in "$KIT"/lib/*.sh; do copy "lib/${f##*/}"; done
while IFS= read -r f; do
  copy "${f#"$KIT"/}"
done < <(cd "$KIT" && find dashboard -type f ! -path '*/__pycache__/*' ! -name '*.pyc' | LC_ALL=C sort | sed "s|^|$KIT/|")
for f in "$KIT"/prompts/*.md; do
  [[ -e "$target/prompts/${f##*/}" ]] || copy "prompts/${f##*/}"
done
chmod +x "$target/factory.sh" "$target/doctor.sh"

if [[ ${#changed[@]} -eq 0 ]]; then
  echo "sync: $target already has this kit"
else
  echo "sync: updated ${#changed[@]} file(s) in $target:"
  printf '  %s\n' "${changed[@]}"
  echo "Review with git -C $target diff, then commit."
fi
