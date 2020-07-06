# Nest Hub (1st gen) Fuchsia package repository mirror

A git rebuild of Google's Fuchsia package repository for the 1st-generation Nest Hub (board `astro`), made for exploring. The source is the TUF repository at `a3i1gkkxw4t8hleigzvg15pn8.fuchsia-updates.googleusercontent.com`, with blobs from `fuchsia-blobs.googleusercontent.com`.

Nothing from the source was dropped. What could not be retrieved is listed in [MISSING.md](MISSING.md). Blob bytes stay on Google's servers: every file that is not small text is a pointer file that records the blob's merkle root, size and URL, and [tools/fetch_blob.py](tools/fetch_blob.py) downloads and verifies it.

## Two views of the same data

| Branch | What it is | One commit per |
|---|---|---|
| `main` | The repo's real publish history, one TUF `targets.json` version at a time, in order | changed target within a publish, then one `publish` commit per TUF version |
| `lines/main` | Release-line trunk: canary candidate-1 builds, each a full system snapshot | changed package version, then one `build` commit per build version |
| `lines/releases/<M.D.R>` | Every later candidate of a release line | same as above |
| `lines/variants/<version>-<k>` | Channel-specific package sets for the few versions that have them | one commit per variant |
| `lines/republished/<version>-<channel>` | A build's replacement update package, branched from the build as first published | changed package version, then the re-publish |

Tags:

- `tuf/v<N>`: the `main` commit that publishes TUF targets version N
- `v/<version>`: the build commit for a Fuchsia version on the `lines/*` branches
- `ch/<variant>-<channel>/<version>`: the commit that build shipped as on that channel, as first published
- `republished/<variant>-<channel>/<version>/<n>`: the nth replacement of that build

## Layout

On `main`:

- `tuf/` holds `targets.json` and `snapshot.json` exactly as published at each version, `root.json` (v4, the only one served) and the current `timestamp.json`.
- `named/<package>/` is the package each per-name target pointed to at that moment.
- `builds/F<milestone>/<version>/<variant>-<channel>/` is each update package (build manifest).

On `lines/*`:

- `packages/<name>/` is every package the build pins in `packages.json`. Channels of one build share these.
- `update/<variant>-<channel>/update-package/` is the update package of each channel that shipped this version.
- `update/<variant>-<channel>/images/<name>/` is each image package that channel's `images.json` references (boot image, vbmeta, firmware, recovery). Channels of one build usually ship different image packages, so each channel keeps its own.
- `BUILD.json` holds the version, milestone, branch date, first publish time, and per channel its target, update package and image packages.

Inside every package folder:

- `PACKAGE.json` describes the package version: meta.far merkle, size and URL, `meta/package`, and counts.
- `meta/...` holds the meta.far entries. Text entries are stored as-is; binary entries are `<path>.ptr.json`. Compiled component manifests also get `<path>.strings.txt`, their printable strings (derived, listed in `PACKAGE.json`).
- `files/...` holds the package's content files. UTF-8 text up to 1 MB is stored as-is; everything else is `<path>.ptr.json`.

See [SCHEMA.md](SCHEMA.md) for the pointer format. ELF summaries of binaries are added on a separate `summaries` branch, keyed by blob merkle, so the mirror's history never needs rewriting.

## Exploring

```sh
git log --oneline lines/main -- packages/netstack3      # every version of one package on the trunk
git diff v/33.20261022.103.1 v/34.20261101.103.1 --stat  # what changed between two builds
git log main -- named/config-data                        # how a per-name target moved over time
git show tuf/v13221:tuf/targets.json                     # a published targets.json, byte for byte
python3 tools/fetch_blob.py packages/netstack3/files/bin/netstack3.ptr.json   # fetch and verify a binary
```

GitHub's Commits page shows at most 10,000 commits per branch. Use `git log` locally, or browse per path and per tag, for the full history.

## How the source was translated

- **Commit times.** Each TUF `targets.json` expires exactly 50 years after what is evidently its signing time, so commit times are the expiry minus 50 years. This is inferred from a consistent pattern, not a documented field. Every publish commit records the raw expiry.
- **Order within a publish or build.** The source has no order below the publish level, so commits run alphabetically by target or package name, all at the publish's time.
- **Release lines without a trunk base** branch from the latest trunk build on or before their first build. F0 to F6 have no canary channel, so the trunk is seeded with each of their release lines' earliest build. Every case is in [BASES.md](BASES.md).
- **Channel-specific package sets.** When channels of one version pin different packages, the set that includes the canary channel (or else the first channel alphabetically) is on the line, and each other set is a side commit. See [VARIANTS.md](VARIANTS.md).
- **Re-published builds.** Release lines show every build as it was first published. When an update package was later replaced with different content, a `lines/republished/...` side branch applies the replacement at its re-publish time. Entry edits that left the package itself unchanged (for example TUF v3050, which dropped the sha512 hash from 2,915 target entries) get no extra commit on the release lines; they show in `tuf/targets.json` on `main`. All of them are listed in [REPUBLISHED.md](REPUBLISHED.md), and every version is on `main`.
- **One clock anomaly.** At TUF v5399 the inferred signing time is about 14 hours earlier than v5398's. The commits keep the inferred times as they are.
- **DRM and key packages** (Widevine, PlayReady, the Netflix keys package, OEMCrypto, trusted apps, cast and weave auth, the OP-TEE and TEE client packages) are recorded as file lists and pointers only. No text is inlined from them, and files containing a private-key marker are never inlined from any package.
