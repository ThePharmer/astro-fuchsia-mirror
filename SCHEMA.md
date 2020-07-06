# Pointer and package file schema

## `*.ptr.json`, version `fuchsia-mirror/pointer@1`

A content blob:

```json
{
  "schema": "fuchsia-mirror/pointer@1",
  "kind": "blob",
  "merkle": "<64 hex: Fuchsia merkle root of the blob>",
  "url": "https://fuchsia-blobs.googleusercontent.com/<merkle>",
  "size": 901152,
  "magic": "<first 16 bytes, hex>",
  "status": "ok",
  "restricted": false,
  "summary": null
}
```

An entry inside a package's meta.far:

```json
{
  "schema": "fuchsia-mirror/pointer@1",
  "kind": "far-entry",
  "far_merkle": "<merkle of the meta.far>",
  "far_url": "https://fuchsia-blobs.googleusercontent.com/<merkle>",
  "path": "meta/example.cm",
  "size": 6776,
  "sha256": "<sha256 of the entry bytes>",
  "restricted": false,
  "summary": null
}
```

- `status` is `ok`, an HTTP status, or `not probed`. Anything other than `ok` is also listed in MISSING.md.
- `note` appears when there is something to say, for example a text file left as a pointer because it contains a private-key marker.
- `restricted: true` marks DRM and key packages, recorded as pointers only.
- `summary` is always `null` in pointer files, so that history never has to be rewritten. Binary summaries live on the separate `summaries` branch instead (see below).

## `PACKAGE.json`, version `fuchsia-mirror/package@1`

```json
{
  "schema": "fuchsia-mirror/package@1",
  "name": "a11y-manager",
  "status": "ok",
  "meta_far": {"merkle": "...", "size": 24576, "url": "..."},
  "meta_package": "{\"name\":\"a11y-manager\",\"version\":\"0\"}",
  "restricted": false,
  "content_files": 36,
  "meta_entries": 4,
  "inline_text_files": 33,
  "pointer_files": 7,
  "derived_files": ["meta/a11y-manager.cm.strings.txt"]
}
```

`meta/contents` inside each folder is the package's authoritative file list, `path=merkle` per line, exactly as in the meta.far.

## Verifying

The merkle root is Fuchsia's: 8 KiB blocks, SHA-256 over a 12-byte identity (little-endian u64 of offset OR level, then u32 length) plus the zero-padded block; upper levels hash 8 KiB groups of digests with length 8192. `tools/fetch_blob.py` implements it and refuses any download that does not match.

## Binary summaries (`summaries` branch)

ELF summaries are kept apart from the mirrored history, keyed by content: `summaries/<first two hex>/<merkle>.json` on the `summaries` branch, one file per unique blob merkle. Any pointer at any commit maps to its summary by its `merkle` field, and summaries can be added or improved without touching the mirror's history.

Planned fields (version `fuchsia-mirror/elf-summary@1`): architecture, role (executable, shared library, driver, Dart AOT snapshot), build ID, `DT_NEEDED` libraries, soname, stripped or not, language fingerprint (Rust, C++, C, Go, Dart), and, where the whole file was scanned, third-party version banners. DRM and key packages get the structural fields only.
