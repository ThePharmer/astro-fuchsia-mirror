# mirror-state

Not part of the mirror's content. This branch holds what the daily sync needs to add new TUF publishes to the
other branches without rebuilding them:

- `state.json`: the newest mirrored TUF version, the expected tips of `main` and `condensed`, where every build
  version and channel lives on the `lines/*` branches, the trunk order, the release-line bases, and the merkles
  the source failed to serve.
- `tags.txt`: every tag of the mirror (`<commit> refs/tags/<name>`). The sync records tags here because the cloud
  sessions that run it are not allowed to create tags on GitHub.
- `tools/sync.py`: the sync itself (with the rendering and fetch modules it uses). It only appends commits; it
  keeps hand edits you make on `main` (README and any other file it does not manage: not `tuf/`, `builds/`, `named/` or the generated tables) and copies them to `condensed`;
  it stops without pushing if `main` was rewritten or a hand edit touches a managed file, if `condensed` moved, if a targets.json does not match its snapshot, or if any
  check on the result fails. All branches and this one are updated in one atomic push.
- `tools/run_sync.sh`: how the scheduled task runs it.
- `tools/push_tags.sh`: run it on your own machine to push the tags in `tags.txt` that GitHub does not have yet.

How builds are placed and what happens to channels that arrive later is described in the mirror's README and
LATE_CHANNELS.md on `main`.
