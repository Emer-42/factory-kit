# shellcheck shell=bash
# lib/events.sh — machine-readable run events for the panel, and the ways a run ends.
# Sourced by factory.sh. Events go to .factory/logs/events.jsonl, one JSON object per line.

EVENTS=".factory/logs/events.jsonl"
CURRENT_PHASE=""
ENDED=""
ON_STOP=""  # a function to call when the run stops early (factory.sh parks the run branch)

# emit <event> [key=value ...]: append one JSON line. Never fails the run.
emit() {
  local -a args=(-nc --arg event "$1" --argjson ts "$(date +%s)")
  # shellcheck disable=SC2016  # jq variables, not shell ones
  local filter='{ts: $ts, event: $event}' kv key
  shift
  for kv in "$@"; do
    key="${kv%%=*}"
    args+=(--arg "$key" "${kv#*=}")
    filter+=" + {$key: \$$key}"
  done
  jq "${args[@]}" "$filter" >>"$EVENTS" 2>/dev/null || true
}

# die <message lines...>: stop the run, tell the panel why.
die() {
  local msg="$1"
  printf '\n✗ %s\n' "$msg" >&2
  shift
  [[ $# -eq 0 ]] || printf '%s\n' "$@" >&2
  ENDED=1
  emit fail phase="$CURRENT_PHASE" reason="$msg"
  [[ -z "$ON_STOP" ]] || "$ON_STOP"
  exit 1
}

finish_run() {
  ENDED=1
  emit finish "$@"
}

# Any exit that is not a die() or finish_run() (Ctrl+C, a failed command) still tells the panel.
on_exit() {
  [[ -z "$ENDED" ]] || return 0
  ENDED=1
  [[ ! -d .factory/logs ]] || emit fail phase="$CURRENT_PHASE" reason="stopped: interrupted or a command failed"
  [[ -z "$ON_STOP" ]] || "$ON_STOP"
}

install_traps() {
  trap on_exit EXIT
  trap 'exit 130' INT TERM
}
