#!/usr/bin/env bash
# Build the static online demo and publish it to the gh-pages branch, which GitHub Pages serves.
#
# From the project root, with the virtual environment active:
#   scripts/deploy_pages.sh               build site/ (about 10 minutes) then publish it
#   scripts/deploy_pages.sh --reuse-data  only app/ changed: refresh the page files, keep the snapshot (seconds)
#   scripts/deploy_pages.sh --no-build    publish the existing site/ as it is
#
# Environment: PYTHON (default: python), REMOTE (default: origin).
# Your working tree is not touched: gh-pages is updated in a temporary git worktree.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python}
REMOTE=${REMOTE:-origin}
SOURCE=$(git rev-parse --short HEAD)

case "${1:-}" in
  --no-build) ;;
  --reuse-data) "$PYTHON" scripts/build_static_site.py --out site --reuse-data ;;
  "") "$PYTHON" scripts/build_static_site.py --out site ;;
  *) echo "Unknown option: $1 (use --reuse-data or --no-build)" >&2; exit 2 ;;
esac
[[ -f site/index.html && -f site/data/health.json ]] || { echo "site/ is not a complete build: run scripts/build_static_site.py" >&2; exit 1; }

WORK=$(mktemp -d)
cleanup() { git worktree remove --force "$WORK" >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT

git fetch --quiet "$REMOTE" gh-pages 2>/dev/null || true
if git show-ref --verify --quiet "refs/remotes/$REMOTE/gh-pages"; then
  git worktree add --quiet -B gh-pages "$WORK" "$REMOTE/gh-pages"
elif git show-ref --verify --quiet refs/heads/gh-pages; then
  git worktree add --quiet "$WORK" gh-pages
else
  git worktree add --quiet --detach "$WORK"
  git -C "$WORK" checkout --quiet --orphan gh-pages
  git -C "$WORK" rm -r --quiet --cached . >/dev/null
fi

# Replace the branch contents with the fresh build.
find "$WORK" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R site/. "$WORK"/
git -C "$WORK" add -A
if git -C "$WORK" diff --cached --quiet; then
  echo "gh-pages already matches this build; nothing to publish."
  exit 0
fi
git -C "$WORK" commit --quiet -m "Publish the online demo built from $SOURCE"
git -C "$WORK" push "$REMOTE" gh-pages
echo "Published gh-pages from $SOURCE."
