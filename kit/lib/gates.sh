# shellcheck shell=bash
# lib/gates.sh — participant gates. Every file in gates/ runs after phase 3, before review.
# Exit 0 passes; anything else stops the run and its output becomes the rejection reason.
# A gate gets FACTORY_BASE (the commit the run started from), FACTORY_ROOT (the repo) and
# FACTORY_CHANGED (the files the agents changed, one per line). Sourced by factory.sh.

GATE_OUTPUT_LINES=40

# _with_timeout <seconds> <cmd...>: run cmd, return 124 if it is still running after <seconds>.
# Built in, so a hanging gate never freezes a run on a machine without coreutils.
_with_timeout() {
  local secs="$1" pid ticks=0
  shift
  "$@" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if ((ticks >= secs * 10)); then
      kill -TERM "$pid" 2>/dev/null || true
      sleep 0.2
      kill -KILL "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    sleep 0.1
    ticks=$((ticks + 1))
  done
  wait "$pid"
}

# _gate_failed <name> <reason>: record the stop and write the rejecting review.
_gate_failed() {
  STOPPED_BY="gate:$1"
  emit gate name="$1" ok=false
  # shellcheck disable=SC2016  # literal backticks: a Markdown code fence
  printf '# Gate %s stopped the run\n\n```\n%s\n```\n\nVERDICT: REJECT\n' "$1" "$2" >.factory/review.md
  printf '\n✗ gate %s stopped the run:\n%s\n' "$1" "$2" >&2
}

# run_gates: run every gate in name order; returns 1 at the first one that fails.
run_gates() {
  local f name log status changed LC_ALL=C
  [[ -d gates ]] || return 0
  changed="$(git -c core.quotepath=off diff --no-renames --name-only "$FACTORY_BASE")"
  for f in gates/*; do
    name="${f##*/}"
    case "$name" in .* | README*) continue ;; esac
    [[ -f "$f" ]] || continue
    log=".factory/logs/gate-$name.log"
    if [[ ! -x "$f" ]]; then
      _gate_failed "$name" "gates/$name is not executable: chmod +x gates/$name && git commit -am \"make gate executable\""
      return 1
    fi
    if head -n 1 "$f" | grep -q $'\r$'; then
      _gate_failed "$name" "gates/$name has Windows line endings: run  sed -i.bak 's/\\r\$//' gates/$name  (or save it as LF), then commit"
      return 1
    fi
    status=0
    (
      export FACTORY_BASE FACTORY_ROOT="$ROOT" FACTORY_CHANGED="$changed"
      _with_timeout "$GATE_TIMEOUT" "./$f" </dev/null >"$log" 2>&1
    ) || status=$?
    if [[ $status -eq 124 ]]; then
      _gate_failed "$name" "gates/$name timed out after ${GATE_TIMEOUT}s"$'\n'"$(head -n "$GATE_OUTPUT_LINES" "$log")"
      return 1
    elif [[ $status -ne 0 ]]; then
      _gate_failed "$name" "$(head -n "$GATE_OUTPUT_LINES" "$log")"
      return 1
    fi
    emit gate name="$name" ok=true
  done
}
