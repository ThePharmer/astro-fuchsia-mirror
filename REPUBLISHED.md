# Re-published builds

Builds whose update package was replaced after it was first published. Release lines show each build as first published;
a content change gets a `lines/republished/...` side branch that applies the replacement, so `git diff ch/<channel>/<version> republished/<channel>/<version>/<n>` shows it.
Every version of every update package is also on `main`.

| Build | Re-published (TUF version) | What changed | Side branch |
|---|---|---|---|
| update-smart-display-user-astro-size-limits-1.20210119.2.1406-prodfood-test | v163 | packages | lines/republished/1.20210119.2.1406-user-astro-size-limits-prodfood-test |
| update-smart-display-user-astro-size-limits-1.20210119.2.1390058-prodfood-test | v167 | packages | lines/republished/1.20210119.2.1390058-user-astro-size-limits-prodfood-test |
| update-smart-display-user-astro-9.20221010.3.176-dogfood-test-signed | v2857 | images.json.orig | lines/republished/9.20221010.3.176-user-astro-dogfood-test-signed |
| update-smart-display-user-astro-10.20221207.2.94-prodfood-test | v2813 | images.json | lines/republished/10.20221207.2.94-user-astro-prodfood-test |
| update-smart-display-user-astro-11.20230306.3.134-prodfood-test | v3722 | firmware, firmware_bl2, fuchsia.vbmeta, images.json, images.json.orig, recovery, recovery.vbmeta, zbi | lines/republished/11.20230306.3.134-user-astro-prodfood-test |
| update-smart-display-user-astro-11.20230306.3.135-prodfood-hotpatch-test | v3883 | firmware, firmware_bl2, fuchsia.vbmeta, images.json, images.json.orig, recovery, recovery.vbmeta, zbi | lines/republished/11.20230306.3.135-user-astro-prodfood-hotpatch-test |
| update-smart-display-user-astro-15.20231018.3.4-dogfood-test-signed | v4604 | images.json, images.json.orig, packages.json | lines/republished/15.20231018.3.4-user-astro-dogfood-test-signed |
| update-smart-display-user-astro-15.20231018.3.6-dogfood-test-signed | v4642 | images.json, images.json.orig, packages.json | lines/republished/15.20231018.3.6-user-astro-dogfood-test-signed |
| update-smart-display-user-astro-16.20231029.3.1-canary-signed | v4570 | images.json, images.json.orig, packages.json | lines/republished/16.20231029.3.1-user-astro-canary-signed |
| update-smart-display-user-astro-16.20231129.3.1-canary-test-signed | v4783 | images.json, images.json.orig, packages.json | lines/republished/16.20231129.3.1-user-astro-canary-test-signed |
| update-smart-display-user-astro-16.20231129.3.1-prodfood-preview | v4784 | images.json, images.json.orig, packages.json | lines/republished/16.20231129.3.1-user-astro-prodfood-preview |

## Target entries edited without changing the package

These TUF versions changed build entries' metadata (for example dropping the sha512 hash) while the package merkle stayed the same. The change is visible in `tuf/targets.json` at that version; no package changed.

| TUF version | Build entries edited |
|---|---|
| v3050 | 2753 |
