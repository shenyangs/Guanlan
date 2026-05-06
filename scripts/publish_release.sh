#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REMOTE="${GUANLAN_RELEASE_REMOTE:-origin}"
BRANCH="${GUANLAN_RELEASE_BRANCH:-main}"
SKIP_GATE="${GUANLAN_RELEASE_SKIP_GATE:-0}"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' pyproject.toml | head -1)"

fail() {
  echo "publish-release failed: $*" >&2
  exit 1
}

[ -n "$VERSION" ] || fail "pyproject.toml version not found"

current_branch="$(git branch --show-current 2>/dev/null || true)"
[ "$current_branch" = "$BRANCH" ] || fail "expected branch $BRANCH, got ${current_branch:-detached}"

if [ "$SKIP_GATE" = "1" ]; then
  scripts/pre_release_status.sh "$VERSION"
else
  scripts/release_gate.sh
fi

git diff --quiet || fail "working tree has unstaged changes after release gate"
git diff --cached --quiet || fail "working tree has staged changes after release gate"

tag="v$VERSION"
if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  fail "local tag already exists: $tag"
fi
if git ls-remote --exit-code --tags "$REMOTE" "$tag" >/dev/null 2>&1; then
  fail "remote tag already exists: $tag"
fi

git push "$REMOTE" "HEAD:$BRANCH"
git tag -a "$tag" -m "发布 Guanlan $tag"
git push "$REMOTE" "$tag"

cat <<EOF
publish-release ok
version=$VERSION
branch=$BRANCH
tag=$tag

Next checks:
  gh run list --workflow release-pypi.yml --limit 3
  python3 -m pip index versions guanlan
  brew update && brew info shenyangs/tap/guanlan
EOF
