# shellcheck shell=bash
# lib/github.sh — the fork-aware ending: push to the participant's fork, open the PR upstream.
# Every run that reaches a verdict opens a PR: APPROVE → ready PR, REJECT → draft "[REJECTED] …".
# The first body line is the run marker the room board reads (docs/run-contract.md).

FORK_OWNER=""

origin_slug() {  # owner/name of origin when it is a GitHub URL (https or ssh), else empty
  local url
  url="$(git config --get remote.origin.url || true)"  # raw: get-url would apply insteadOf rewrites
  case "$url" in
    *github.com[:/]*) url="${url#*github.com[:/]}"; echo "${url%.git}" ;;
  esac
}

# detect_upstream: set UPSTREAM (the workshop repo this fork came from) and FORK_OWNER.
# The fork is named explicitly: with an `upstream` remote present, plain `gh repo view`
# would look at upstream itself, which has no parent.
detect_upstream() {
  local slug
  if [[ -n "${FACTORY_UPSTREAM:-}" ]]; then  # organiser rehearsal: GitHub cannot fork your own repo
    UPSTREAM="$FACTORY_UPSTREAM"
    FORK_OWNER="${UPSTREAM%%/*}"
    git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "https://github.com/$UPSTREAM.git"
    return 0
  fi
  slug="$(origin_slug)"
  # shellcheck disable=SC2086  # $slug is empty or one owner/name word
  UPSTREAM="$(gh repo view $slug --json parent \
    -q 'if .parent then .parent.owner.login + "/" + .parent.name else "" end' 2>/dev/null || true)"
  [[ -n "$UPSTREAM" ]] || die "this repo is not a fork of a workshop repo: fork it on GitHub and clone your fork"
  git remote get-url upstream >/dev/null 2>&1 || git remote add upstream "https://github.com/$UPSTREAM.git"
  FORK_OWNER="${slug%%/*}"
  [[ -n "$FORK_OWNER" ]] || FORK_OWNER="$(gh api user --jq .login 2>/dev/null || true)"
  [[ -n "$FORK_OWNER" ]] || die "could not read your GitHub login: gh auth status"
}

branch_taken() {  # locally or on the fork
  git show-ref --quiet "refs/heads/$1" || git ls-remote --exit-code --heads origin "$1" >/dev/null 2>&1
}

# compute_tier: what the participant changed on top of the workshop repo.
# 3 = a prompt, 2 = a gate, 1 = neither.
compute_tier() {
  local ref="upstream/main" changed
  git fetch -q upstream main 2>/dev/null || ref="origin/main"
  changed="$(git diff --name-only "$ref...$FACTORY_BASE" 2>/dev/null || true)"
  if grep -q '^prompts/' <<<"$changed"; then
    echo 3
  elif grep -q '^gates/' <<<"$changed"; then
    echo 2
  else
    echo 1
  fi
}

run_marker() {  # run_marker <verdict>: the board's one-line summary of this run
  local json
  # shellcheck disable=SC2016  # jq variables
  json="$(jq -nc --argjson ticket "$ISSUE" --arg verdict "$1" --arg stopped "$STOPPED_BY" \
    --argjson turns "$TOTAL_TURNS" --argjson cost "$TOTAL_COST" --arg model "$MODEL" \
    --argjson tier "$(compute_tier)" \
    '{v: 1, ticket: $ticket, verdict: $verdict, stopped_by: (if $stopped == "" then null else $stopped end),
      turns: $turns, cost: $cost, model: $model, tier: $tier}')"
  printf '<!-- factory-run %s -->\n' "$json"
}

shell_words() {  # a command line a person can copy: quote only the words that need it
  local word out=""
  for word in "$@"; do
    if [[ "$word" =~ ^[A-Za-z0-9_./:=@+-]+$ ]]; then
      out+="$word "
    else
      out+="'$(printf '%s' "$word" | sed "s/'/'\\\\''/g")' "
    fi
  done
  echo "${out% }"
}

write_pr_body() {  # write_pr_body <verdict> <file>
  local zwsp=$'\xe2\x80\x8b'
  {
    run_marker "$1"
    if [[ "$1" == "APPROVE" ]]; then
      printf 'Closes #%s\n\n' "$ISSUE"
    else
      printf 'Rejected run for #%s (not closing it).\n\n' "$ISSUE"
    fi
    printf '## Review\n\n'
    cat .factory/review.md
    if [[ -s .factory/report.md ]]; then
      printf '\n\n## Test and security report\n\n'
      cat .factory/report.md
    fi
    if [[ -s .factory/plan.md ]]; then
      printf '\n\n<details><summary>Plan</summary>\n\n'
      cat .factory/plan.md
      printf '\n</details>\n'
    fi
  } >"$2.tmp"
  # Agent-written text: defuse @mentions (no surprise notifications), stay under GitHub's limit.
  sed -E "s/@([A-Za-z0-9_-])/@${zwsp}\\1/g" "$2.tmp" | head -c 60000 >"$2"
  rm -f "$2.tmp"
}

# open_pr <verdict>: commit, push to the fork, open the PR against the workshop repo.
open_pr() {
  local verdict="$1" body=".factory/pr-body.md" title="$ISSUE_TITLE" url result="pr"
  local -a draft=()
  if [[ "$verdict" != "APPROVE" ]]; then
    title="[REJECTED] $ISSUE_TITLE"
    draft=(--draft)
    result="rejected"
  fi
  commit_run
  write_pr_body "$verdict" "$body"
  git push -q --no-verify -u origin "$BRANCH" || die "could not push to your fork (origin): run ./doctor.sh"
  local -a create=(gh pr create --repo "$UPSTREAM" --base main --head "$FORK_OWNER:$BRANCH" --title "$title"
    --body-file "$body" ${draft[@]+"${draft[@]}"})
  url="$("${create[@]}")" || die "pushed, but gh pr create failed (network?). Retry, from main:" "$(shell_words "${create[@]}")"
  printf '\n%s\n' "$url"
  finish_run result="$result" url="$url" verdict="$verdict" stopped_by="$STOPPED_BY" \
    turns="$TOTAL_TURNS" cost="$TOTAL_COST"
}
