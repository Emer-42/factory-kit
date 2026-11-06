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

# gate_problem <file>: prints why a gate cannot run (not executable, Windows line endings), if it cannot.
gate_problem() {
  local name="${1##*/}"
  if [[ ! -x "$1" ]]; then
    echo "gates/$name is not executable: chmod +x gates/$name && git commit -am \"make gate executable\""
  elif head -n 1 "$1" | grep -q $'\r$'; then
    echo "gates/$name has Windows line endings: perl -pi -e 's/\\r\$//' gates/$name && git commit -am \"gate: LF line endings\""
  fi
}

gate_files() {  # the gates that run, in name order (not READMEs, dotfiles or editor/sed backups)
  local f name LC_ALL=C
  [[ -d gates ]] || return 0
  for f in gates/*; do
    name="${f##*/}"
    case "$name" in .* | README* | *.bak | *~ | *.orig | *.swp) continue ;; esac
    [[ -f "$f" ]] && echo "$f"
  done
}

# check_gate_files: the first gate problem, for preflight and doctor (before any phase is paid for).
check_gate_files() {
  local f problem
  while IFS= read -r f; do
    problem="$(gate_problem "$f")"
    if [[ -n "$problem" ]]; then
      echo "$problem"
      return 1
    fi
  done < <(gate_files)
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
  local f name log status changed problem
  changed="$(git -c core.quotepath=off diff --no-renames --name-only "$FACTORY_BASE")"
  while IFS= read -r f; do
    name="${f##*/}"
    log=".factory/logs/gate-$name.log"
    problem="$(gate_problem "$f")"
    if [[ -n "$problem" ]]; then
      _gate_failed "$name" "$problem"
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
  done < <(gate_files)
}
