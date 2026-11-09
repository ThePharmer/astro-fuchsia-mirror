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
