#!/usr/bin/env bash
# check-problem-repo.sh — verify a workshop problem repo before publishing it. Spends no tokens.
# Usage: scripts/check-problem-repo.sh <repo-dir> [--trip <patch> <gate-file-name|review>]... [--pass <patch>]...
#
# Works on a fresh clone of what is committed, the way a participant gets it:
#   clean     the source repo is on main with nothing uncommitted
#   kit       sync.sh would change nothing (the repo has this kit)
#   conf      factory.conf loads
#   tests     SETUP then TEST_CMD pass, and leave nothing git does not ignore
#   lint      LINT_CMD passes (when set)
#   gates     every shipped gate is runnable and passes on main
#   trip      each --trip patch (what an agent might write for the trap ticket), run the way the
#             engine runs it: tests and lint pass, nothing changes outside SCOPE, then the named
#             gate stops it first; "review" means no gate does, so the reviewer gets to reject it
#   pass      each --pass patch (a plausible solution of an ordinary ticket) gets through the same
#             way with no gate stopping it
set -uo pipefail

KIT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
repo="${1:?usage: check-problem-repo.sh <repo-dir> [--trip <patch> <gate>]...}"
repo="$(cd "$repo" && pwd)"
shift
FAILS=0
ok() { printf 'ok   %s\n' "$1"; }
fail() {
  printf 'FAIL %s: %s\n' "$1" "$2"
  FAILS=$((FAILS + 1))
}

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
clone="$work/repo"

# clean
if [[ "$(git -C "$repo" branch --show-current)" != "main" ]]; then
  fail "clean" "not on main"
elif [[ -n "$(git -C "$repo" status --porcelain)" ]]; then
  fail "clean" "uncommitted changes: $(git -C "$repo" status --short | tr '\n' ' ')"
else
  ok "clean"
fi

# Read the --trip/--pass arguments now: their paths are relative to where the checker was started.
declare -a PATCHES=() EXPECT=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --trip) [[ $# -ge 3 ]] || { echo "usage: --trip <patch> <gate-file-name|review>" >&2; exit 2; }
      PATCHES+=("$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"); EXPECT+=("$3"); shift 3 ;;
    --pass) [[ $# -ge 2 ]] || { echo "usage: --pass <patch>" >&2; exit 2; }
      PATCHES+=("$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"); EXPECT+=("-"); shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

git clone -q "$repo" "$clone" || { fail "clone" "git clone failed"; exit 1; }
cd "$clone" || exit 1

# kit
bash "$KIT_ROOT/sync.sh" "$clone" >/dev/null 2>&1
if [[ -n "$(git status --porcelain)" ]]; then
  fail "kit" "out of date, run sync.sh: $(git status --short | tr '\n' ' ')"
  git checkout -q -- . && git clean -fdq
else
  ok "kit"
fi

# conf, in a subshell that keeps the kit's die from ending this script
die() {
  printf '%s\n' "$1" >&2
  exit 1
}
# shellcheck disable=SC2329  # called by the sourced libraries
emit() { :; }
# shellcheck source=../kit/lib/conf.sh
source lib/conf.sh
# shellcheck source=../kit/lib/gates.sh
source lib/gates.sh
if msg="$( (load_conf) 2>&1 >/dev/null)"; then
  load_conf
  ok "conf"
else
  fail "conf" "$msg"
  echo "check: $FAILS failure(s)"
  exit 1
fi

# tests
if [[ -n "$SETUP" ]] && ! bash -c "$SETUP" >"$work/setup.log" 2>&1; then
  fail "tests" "SETUP failed ($SETUP): $(tail -n 3 "$work/setup.log" | tr '\n' ' ')"
elif ! bash -c "$TEST_CMD" >"$work/tests.log" 2>&1; then
  fail "tests" "TEST_CMD fails on a fresh clone ($TEST_CMD): $(tail -n 3 "$work/tests.log" | tr '\n' ' ')"
elif [[ -n "$(git status --porcelain)" ]]; then
  fail "tests" "SETUP/TEST_CMD leave files git does not ignore: $(git status --short | tr '\n' ' ')"
else
  ok "tests"
fi

# lint: agents must start from a green lint, or every run argues with it
if [[ -n "$LINT_CMD" ]]; then
  if bash -c "$LINT_CMD" >"$work/lint.log" 2>&1; then
    ok "lint"
  else
    fail "lint" "LINT_CMD fails on a fresh clone ($LINT_CMD): $(tail -n 3 "$work/lint.log" | tr '\n' ' ')"
  fi
fi

run_all_gates() {  # prints the name of the first gate that fails, if any
  local f
  while IFS= read -r f; do
    # shellcheck disable=SC2031  # exported for the gate only, on purpose
    if ! (export FACTORY_BASE="$1" FACTORY_ROOT="$clone" FACTORY_CHANGED="$2"; "./$f" </dev/null >/dev/null 2>&1); then
      echo "${f##*/}"
      return
    fi
  done < <(gate_files)
}

# gates
base="$(git rev-parse HEAD)"
if problem="$(check_gate_files)"; then
  failing="$(run_all_gates "$base" "")"
  if [[ -n "$failing" ]]; then fail "gates" "gates/$failing fails on main"; else ok "gates"; fi
else
  fail "gates" "$problem"
fi

# trip and pass: apply the patch, then do what the engine does after phase 2
out_of_scope() {  # the changed files (stdin) that SCOPE does not allow
  local f
  while IFS= read -r f; do
    [[ -z "$f" ]] || in_scope "$f" || echo "$f"
  done
}

i=0
while [[ $i -lt ${#PATCHES[@]} ]]; do
  patch="${PATCHES[$i]}" gate="${EXPECT[$i]}"
  i=$((i + 1))
  label="trip ${patch##*/}"
  [[ "$gate" != "-" ]] || label="pass ${patch##*/}"
  if ! git apply "$patch" 2>"$work/apply.log"; then
    fail "$label" "patch does not apply: $(tr '\n' ' ' <"$work/apply.log")"
    continue
  fi
  if ! bash -c "$TEST_CMD" >"$work/patched-tests.log" 2>&1; then
    fail "$label" "tests fail with the patch applied: $(tail -n 3 "$work/patched-tests.log" | tr '\n' ' ')"
  elif [[ -n "$LINT_CMD" ]] && ! bash -c "$LINT_CMD" >"$work/patched-lint.log" 2>&1; then
    fail "$label" "lint fails with the patch applied: $(tail -n 3 "$work/patched-lint.log" | tr '\n' ' ')"
  else
    git add -N .
    changed="$(git -c core.quotepath=off diff --no-renames --name-only "$base")"
    outside="$(out_of_scope <<<"$changed")"
    first="$(run_all_gates "$base" "$changed")"
    if [[ -n "$outside" ]]; then
      fail "$label" "the scope check would stop it first (after the tests ran): $(tr '\n' ' ' <<<"$outside")"
    elif [[ "$gate" == "-" && -z "$first" ]]; then
      ok "$label gets through every gate"
    elif [[ "$gate" == "-" ]]; then
      fail "$label" "gates/$first stops a change that should get through"
    elif [[ "$gate" == "review" && -z "$first" ]]; then
      ok "$label reaches the review"
    elif [[ "$gate" == "review" ]]; then
      fail "$label" "expected to reach the review, but gates/$first stopped it"
    elif [[ "$first" == "$gate" ]]; then
      ok "$label stopped by $gate"
    else
      fail "$label" "expected gates/$gate to stop it, got ${first:-no gate}${first:+ (gates/$first)}"
    fi
  fi
  git reset -q && git checkout -q -- . && git clean -fdq
done

if [[ "$FAILS" -eq 0 ]]; then
  echo "check: all ok"
  exit 0
fi
echo "check: $FAILS failure(s)"
exit 1
