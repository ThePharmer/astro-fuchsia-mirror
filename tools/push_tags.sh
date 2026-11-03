#!/usr/bin/env bash
# Pushes the mirror's tags to GitHub (the cloud sessions that build the mirror are not allowed to create tags)
# and removes the leftover _staging/main branch. Every tag points at a commit already on GitHub, so almost
# nothing is uploaded.
#
# usage: bash push_tags.sh      (needs git and your normal GitHub login; run it from any folder)
#
# Makes a commits-only clone in ./nest-hub-fuchsia-mirror.git (no files or trees), reads the full tag list
# from the mirror-state branch (tags.txt), pushes the tags GitHub does not have yet 1000 at a time, then
# checks every tag on GitHub against the list. Safe to re-run; run it again whenever you want new tags.
set -euo pipefail
REPO=${REPO:-https://github.com/ThePharmer/nest-hub-fuchsia-mirror.git}
DIR="$PWD/nest-hub-fuchsia-mirror.git"
if [ ! -d "$DIR" ]; then
  git clone --bare --filter=tree:0 "$REPO" "$DIR"
fi
cd "$DIR"
git fetch --quiet --filter=tree:0 origin '+refs/heads/*:refs/heads/*'
LIST="$DIR/tags.txt"
git show refs/heads/mirror-state:tags.txt > "$LIST"
echo "$(wc -l < "$LIST") tags in the list"

git ls-remote --tags origin | awk '{print $1 " " $2}' | grep -v '\^{}$' | sort > "$DIR/remote_tags.txt"
sort "$LIST" | comm -23 - "$DIR/remote_tags.txt" > "$DIR/todo.txt"
echo "$(wc -l < "$DIR/todo.txt") to push"
awk '{print "update " $2 " " $1}' "$DIR/todo.txt" | git update-ref --stdin
cut -d' ' -f2 "$DIR/todo.txt" | awk '{print "+" $1 ":" $1}' | split -l 1000 - "$DIR/batch_"
n=0
for f in "$DIR"/batch_*; do
  [ -e "$f" ] || continue
  git -c push.negotiate=false push --quiet origin $(cat "$f")
  n=$((n + $(wc -l < "$f"))); echo "  $n pushed"; rm -f "$f"
done

if git ls-remote --exit-code --heads origin _staging/main > /dev/null; then
  echo "removing leftover branch _staging/main"
  git push --quiet origin --delete _staging/main
fi

echo "verifying"
git ls-remote --tags origin | awk '{print $1 " " $2}' | grep -v '\^{}$' | sort > "$DIR/remote_tags.txt"
missing=$(sort "$LIST" | comm -23 - "$DIR/remote_tags.txt" | wc -l)
if [ "$missing" -eq 0 ]; then
  echo "OK: all $(wc -l < "$LIST") tags on GitHub match the list"
else
  echo "MISMATCH: $missing tags missing or different, for example:"; sort "$LIST" | comm -23 - "$DIR/remote_tags.txt" | head -5; exit 1
fi
