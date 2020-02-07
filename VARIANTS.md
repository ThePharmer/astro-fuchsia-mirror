# Channel-specific package sets

Versions whose channels pin different packages. The set that includes the canary channel (else the first channel alphabetically) is on the line; each other set is a side commit.
Channels of one build also ship their own boot and recovery image packages; those live in each channel's folder and are not listed here.

| Version | Side branch | Channels | Packages that differ |
|---|---|---|---|
| 16.20231026.3.1 | lines/variants/16.20231026.3.1-1 | user-astro-canary-test-signed, user-astro-prodfood-preview | build-info, system_image |
| 16.20231029.3.1 | lines/variants/16.20231029.3.1-1 | user-astro-canary-test-signed, user-astro-prodfood-preview, user-astro-teamfood-release-signed | build-info, system_image |
| 16.20231116.3.1 | lines/variants/16.20231116.3.1-1 | user-astro-teamfood-test-signed | build-info, system_image |
| 16.20231117.1.1 | lines/variants/16.20231117.1.1-1 | user-astro-prodfood-hotpatch-test | build-info, system_image |
| 16.20231127.3.1 | lines/variants/16.20231127.3.1-1 | user-astro-teamfood-release-signed | build-info, system_image |
| 16.20231130.3.1 | lines/variants/16.20231130.3.1-1 | user-astro-canary-test-signed, user-astro-prodfood-preview | build-info, system_image |
| 15.20231018.3.4 | lines/variants/15.20231018.3.4-1 | user-astro-prodfood-test | build-info, system_image |
| 15.20231018.3.10 | lines/variants/15.20231018.3.10-1 | user-astro-prodfood-test, user-astro-teamfood-test-signed | build-info, system_image |
