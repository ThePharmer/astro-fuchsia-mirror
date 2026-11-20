# Channels added after their build

The daily sync places each build when it first appears. When another channel ships the same build later, it is added on the build's branch if the build is still that branch's newest, and otherwise on a `lines/late/<version>` side branch that starts from the build's commit. A channel whose package set differs gets a `lines/variants/...` branch instead. The channel tag `ch/<channel>/<version>` points at the commit that added it.

| Build | Channel | First published | Commit is on |
|---|---|---|---|
| 33.20261022.103.1801 | user-with-ota-dogfood-release-signed | v13224 | lines/releases/33.20261022.103 |
| 33.20261022.103.1801 | user-with-ota-dogfood-release-signed-gia | v13225 | lines/releases/33.20261022.103 |
| 34.20261101.103.1 | user-with-ota-canary-release-signed | v13226 | lines/late/34.20261101.103.1 |
| 34.20261101.103.1 | user-with-ota-canary-signed | v13227 | lines/late/34.20261101.103.1 |
| 34.20261101.103.1 | user-with-ota-canary-release-signed-netstack3 | v13228 | lines/late/34.20261101.103.1 |
| 32.20260727.103.13702802 | user-with-ota-preview-stable-channel | v13240 | lines/late/32.20260727.103.13702802 |
| 32.20260727.103.13702802 | user-with-ota-preview-joining-stable-channel | v13241 | lines/late/32.20260727.103.13702802 |
| 33.20261022.103.1801 | user-with-ota-dogfood-release-signed-i18n | v13235 | lines/late/33.20261022.103.1801 |
| 33.20261022.103.1801 | user-with-ota-dogfood-release-signed-i18n-gia | v13236 | lines/late/33.20261022.103.1801 |
| 33.20261022.103.1801 | user-with-ota-prodfood-test | v13244 | lines/late/33.20261022.103.1801 |
| 34.20261102.103.1 | user-with-ota-canary-release-signed | v13237 | lines/late/34.20261102.103.1 |
| 34.20261102.103.1 | user-with-ota-canary-signed | v13238 | lines/late/34.20261102.103.1 |
| 34.20261102.103.1 | user-with-ota-canary-release-signed-netstack3 | v13239 | lines/late/34.20261102.103.1 |
| 32.20260727.103.13702802 | user-with-ota-stable-channel | v13305 | lines/late/32.20260727.103.13702802 |
| 34.20261108.103.1 | user-with-ota-prodfood-hotpatch-test | v13329 | lines/late/34.20261108.103.1 |
| 34.20261108.103.1 | user-with-ota-teamfood-release-signed | v13334 | lines/late/34.20261108.103.1 |
| 34.20261108.103.1 | user-with-ota-teamfood-release-signed-gia | v13335 | lines/late/34.20261108.103.1 |
| 32.20260727.103.13702902 | user-with-ota-prodfood-test | v13341 | lines/releases/32.20260727.103 |
| 32.20260727.103.13702902 | user-with-ota-teamfood-test-signed | v13342 | lines/releases/32.20260727.103 |
| 32.20260727.103.13702902 | user-with-ota-partner-prodfood-minor-release | v13343 | lines/releases/32.20260727.103 |
| 32.20260727.103.13702902 | user-with-ota-prodfood-minor-release-gia | v13344 | lines/releases/32.20260727.103 |
| 32.20260727.103.13702902 | user-with-ota-prodfood-minor-release-signed-gia | v13345 | lines/releases/32.20260727.103 |
| 32.20260727.103.13702902 | user-with-ota-prodfood-minor-release | v13346 | lines/releases/32.20260727.103 |
| 33.20261022.103.3204 | user-with-ota-dogfood-release-signed | v13347 | lines/releases/33.20261022.103 |
| 33.20261022.103.3204 | user-with-ota-dogfood-release-signed-gia | v13348 | lines/releases/33.20261022.103 |
| 33.20261022.103.3204 | user-with-ota-partner-dogfood-release-signed | v13349 | lines/releases/33.20261022.103 |
| 32.20260727.103.13702902 | user-with-ota-partner-prodfood-hotpatch-release | v13372 | lines/releases/32.20260727.103 |
| 32.20260727.103.13702902 | user-with-ota-prodfood-hotpatch-release | v13373 | lines/releases/32.20260727.103 |
| 32.20260727.103.13702902 | user-with-ota-prodfood-hotpatch-release-gia | v13374 | lines/releases/32.20260727.103 |
| 33.20261022.103.3204 | user-with-ota-dogfood-release-signed-i18n | v13368 | lines/releases/33.20261022.103 |
| 33.20261022.103.3204 | user-with-ota-dogfood-release-signed-i18n-gia | v13369 | lines/releases/33.20261022.103 |
| 32.20260727.103.13702802 | user-with-ota-preview-leaving-stable-channel | v13381 | lines/late/32.20260727.103.13702802 |
| 32.20260727.103.13702902 | user-with-ota-preview-joining-stable-channel | v13377 | lines/releases/32.20260727.103 |
| 32.20260727.103.13702902 | user-with-ota-preview-stable-channel | v13378 | lines/releases/32.20260727.103 |
| 34.20261116.103.1 | user-with-ota-canary-release-signed | v13382 | lines/late/34.20261116.103.1 |
| 34.20261116.103.1 | user-with-ota-canary-signed | v13384 | lines/late/34.20261116.103.1 |
| 34.20261116.103.1 | user-with-ota-canary-release-signed-netstack3 | v13385 | lines/late/34.20261116.103.1 |
| 32.20260727.103.13702902 | user-with-ota-stable-channel | v13405 | lines/releases/32.20260727.103 |
| 33.20261022.103.3800 | user-with-ota-dogfood-release-signed | v13400 | lines/releases/33.20261022.103 |
| 33.20261022.103.3800 | user-with-ota-dogfood-release-signed-gia | v13401 | lines/releases/33.20261022.103 |
| 33.20261022.103.3800 | user-with-ota-partner-dogfood-release-signed | v13402 | lines/releases/33.20261022.103 |
| 33.20261022.103.3800 | user-with-ota-dogfood-release-signed-i18n | v13403 | lines/releases/33.20261022.103 |
| 33.20261022.103.3800 | user-with-ota-dogfood-release-signed-i18n-gia | v13404 | lines/releases/33.20261022.103 |
| 34.20261116.103.1 | user-with-ota-teamfood-release-signed | v13406 | lines/late/34.20261116.103.1 |
| 34.20261116.103.1 | user-with-ota-teamfood-release-signed-gia | v13407 | lines/late/34.20261116.103.1 |
| 34.20261118.103.1 | user-with-ota-canary-release-signed | v13408 | lines/late/34.20261118.103.1 |
| 34.20261118.103.1 | user-with-ota-canary-signed | v13409 | lines/late/34.20261118.103.1 |
| 34.20261118.103.1 | user-with-ota-canary-release-signed-netstack3 | v13410 | lines/late/34.20261118.103.1 |
| 34.20261119.103.1 | user-with-ota-canary-release-signed | v13417 | lines/late/34.20261119.103.1 |
| 34.20261119.103.1 | user-with-ota-canary-signed | v13418 | lines/late/34.20261119.103.1 |
| 34.20261119.103.1 | user-with-ota-canary-release-signed-netstack3 | v13419 | lines/late/34.20261119.103.1 |
