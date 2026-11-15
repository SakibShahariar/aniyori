# Commit CI Audit Ledger

Persistent repository-specific record of commit-level CI checks and red-cross investigations.

## How to use this ledger

1. Read this file before auditing commit checks.
2. Check only commits newer than the checkpoint, plus older **red**, **pending**, or explicitly unresolved entries.
3. Record exact commit SHAs and observed results; never infer from missing badges or empty API responses.
4. Preserve failures and append diagnosis, fix, rerun, and final-outcome evidence.
5. Advance the checkpoint only after reviewing the range; carry unresolved entries forward.

## Result meanings

| Result | Meaning |
|---|---|
| **green** | Completed successful check/run directly observed. |
| **red** | Completed failing check/run directly observed. |
| **pending** | Check/run exists but is unfinished. |
| **unavailable** | Available evidence did not expose a result; not a pass or failure. |
| **not applicable** | Workflow configuration confirms no relevant check is triggered. |

## Checkpoint

- Repository: `SakibShahariar/aniyori`
- Default branch: `main`
- Checkpoint SHA: `e661a006d27d10037d25b27236aefb48165bf3a3`
- Initialized: 2026-11-02
- Baseline: latest branch tip queried through combined commit-status endpoint; empty status list recorded as **unavailable**, not green/red. Older history was not retroactively audited during setup.
- Next session: review commits after `e661a006d27d10037d25b27236aefb48165bf3a3`; carry forward any red or unresolved entries.

## Initial baseline

| Commit SHA | Subject | CI result | Checked | Follow-up |
|---|---|---|---|---|
| `e7728683fc28eae13e7af798377a9b90bcbbd769` | Default-branch tip at ledger initialization | unavailable | 2026-11-02 | Combined status lookup returned no entries. Revisit if new run or visible failure evidence appears. |

## Red-cross investigation log

No red result was confirmed from the status data retrieved during setup.

### Failure record template

- Commit SHA:
- Commit subject:
- First observed (date):
- Workflow / run URL:
- Failed job / step:
- Failure summary:
- Classification: regression / pre-existing / inconclusive
- Fix commit(s):
- Rerun attempt(s) and result:
- Final verified outcome:
- Remaining follow-up:

## Session history

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-02 | Initial checkpoint: `e7728683fc28eae13e7af798377a9b90bcbbd769` | Latest commit queried; empty status response recorded as unavailable. Earlier history not retroactively audited. |


## Reviewed range: 2026-11-03

Commits after the previous checkpoint through `bd3f6937d34fba486dd8efd1e6677e8ed7c6ab1f` were checked against their individual GitHub Actions runs. The range contains 13 commits; 12 completed green and one completed red before its follow-up fix.

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `fa6d0c63c457891fb87b86867e6d19a461960f8b` | docs: add persistent commit CI audit ledger | green | [41456867114](https://github.com/SakibShahariar/aniyori/actions/runs/41456867114) |
| `7258a1162b0045f0b3aeb7a5b877f4fb873e5197` | docs: document incremental commit CI auditing | green | [41456873492](https://github.com/SakibShahariar/aniyori/actions/runs/41456873492) |
| `2fe7ac763221170b694a1d1f4e31fe2345e14b1b` | docs: define issue triage categories | green | [41573564119](https://github.com/SakibShahariar/aniyori/actions/runs/41573564119) |
| `60c9a90e7ef11a7839e5f2b5ebf7c8255b96c177` | docs(agents): define administrative commit hygiene | green | [41597861624](https://github.com/SakibShahariar/aniyori/actions/runs/41597861624) |
| `271192a3727568075a529d76316c440b41730593` | fix(anilist): bound GraphQL response size (#83) | green | [41717112480](https://github.com/SakibShahariar/aniyori/actions/runs/41717112480) |
| `5befe653e5ea3062d117f7ab685c27013f00e81d` | test(rss): cover HTTP and malformed feed failures (#83) | green | [41717205730](https://github.com/SakibShahariar/aniyori/actions/runs/41717205730) |
| `70c90973c0189330102fcd84c60f5bbc04f547c9` | docs: explain local data and external requests (#82) | green | [41717391273](https://github.com/SakibShahariar/aniyori/actions/runs/41717391273) |
| `8456c6ecb04d737278bc78ada5e49d3861190ba4` | fix(security): validate cover redirects before requests (#85) | green | [41717559079](https://github.com/SakibShahariar/aniyori/actions/runs/41717559079) |
| `58811580d5c19599b7e47113d2c622f467628d88` | chore: add GPL-3.0-or-later license (#80) | green | [41720307133](https://github.com/SakibShahariar/aniyori/actions/runs/41720307133) |
| `78e16f69b81c037bee1b393af781c083638f401c` | docs: declare GPL-3.0-or-later license (#80) | green | [41720320349](https://github.com/SakibShahariar/aniyori/actions/runs/41720320349) |
| `6d279495345433b804d30352ad65ddc256acbf61` | feat(rss): parse Nyaa torrent metadata (#54) | red | [41721680557](https://github.com/SakibShahariar/aniyori/actions/runs/41721680557) |
| `a0bff0c40c283298c628ca92852d6b1d0128ede3` | fix(rss): preserve release metadata parsing (#54) | green | [41721726377](https://github.com/SakibShahariar/aniyori/actions/runs/41721726377) |
| `bd3f6937d34fba486dd8efd1e6677e8ed7c6ab1f` | feat(rss): add Nyaa search feed setup (#54) | green | [41721865564](https://github.com/SakibShahariar/aniyori/actions/runs/41721865564) |

### Failure investigation

- Commit SHA: `6d279495345433b804d30352ad65ddc256acbf61`
- Workflow / run: [Tests / 41721680557](https://github.com/SakibShahariar/aniyori/actions/runs/41721680557)
- Failed tests: `test_refresh_extracts_all_supported_quality_metadata_when_present` (missing `seeders`) and `test_refresh_preserves_nyaa_torrent_stats_for_result_rows` (missing `file_size_mb`).
- Diagnosis: the new fallback regular expressions were double-escaped, so the existing text-based seeder extraction and new Nyaa size parsing did not match.
- Classification: regression introduced by the Nyaa metadata commit.
- Fix commit: `a0bff0c40c283298c628ca92852d6b1d0128ede3` corrected the regex escaping.
- Rerun / final outcome: the fix commit's complete Tests workflow passed (run [41721726377](https://github.com/SakibShahariar/aniyori/actions/runs/41721726377)).
- Remaining follow-up: none for this regression.

## Session history

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-02 | Initial checkpoint: `e7728683fc28eae13e7af798377a9b90bcbbd769` | Latest commit queried; empty status response recorded as unavailable. Earlier history not retroactively audited. |
| 2026-11-03 | `e7728683fc28eae13e7af798377a9b90bcbbd769` → `bd3f6937d34fba486dd8efd1e6677e8ed7c6ab1f` | Reviewed 13 commits individually: 12 green, 1 red regression fixed by a green follow-up. |


## Reviewed range: 2026-11-03 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `f76856ba2b503ae5f443616f5a9f9597435a7b27` | feat(rss): filter and sort monitored releases (#54) | green | [41722027622](https://github.com/SakibShahariar/aniyori/actions/runs/41722027622) |

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-03 | `bd3f6937d34fba486dd8efd1e6677e8ed7c6ab1f` → `f76856ba2b503ae5f443616f5a9f9597435a7b27` | Reviewed one new commit; CI green. |


### Failure investigation: ordered release rules

- Commit SHA: `c9c3e683921252a3027997c789b5e4e6593337b4`
- Workflow / run: [Tests / 41722271367](https://github.com/SakibShahariar/aniyori/actions/runs/41722271367)
- Failed tests: `test_store_adds_edits_reorders_removes_and_round_trips` and `test_release_rule_store_persists_edits_removals_and_order`.
- Diagnosis: both tests incorrectly treated the result of the first `ReleaseRuleStore.add()` call as if it already contained a second rule. The store correctly returned one rule after the first add.
- Classification: test defect introduced in the issue #43 change; production code compilation succeeded.
- Fix: update tests to capture the result of the second add operation. Also preserve caller order for equal rule priorities, validate rule field/action types, handle absent category collections safely, and rank preferred/wanted matches ahead of unmatched releases.
- Fix commit: `0a1f18b5bd22cb37c51b9dea424c9aa624a88b13`. The complete Tests workflow passed on that commit (run [41722392894](https://github.com/SakibShahariar/aniyori/actions/runs/41722392894)).


## Reviewed range: 2026-11-03 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `c9c3e683921252a3027997c789b5e4e6593337b4` | feat(rss): add ordered smart release rules (#43) | red | [41722271367](https://github.com/SakibShahariar/aniyori/actions/runs/41722271367) |
| `0a1f18b5bd22cb37c51b9dea424c9aa624a88b13` | fix(rss): correct smart rule ordering tests (#43) | green | [41722392894](https://github.com/SakibShahariar/aniyori/actions/runs/41722392894) |

### Failure investigation: ordered release rules

- Commit SHA: `c9c3e683921252a3027997c789b5e4e6593337b4`
- Workflow / run: [Tests / 41722271367](https://github.com/SakibShahariar/aniyori/actions/runs/41722271367)
- Failed tests: `test_store_adds_edits_reorders_removes_and_round_trips` and `test_release_rule_store_persists_edits_removals_and_order`.
- Diagnosis: both tests incorrectly treated the result of the first `ReleaseRuleStore.add()` call as if it already contained a second rule. The store correctly returned one rule after the first add.
- Classification: test defect introduced in the issue #43 change; production code compilation succeeded.
- Fix commit: `0a1f18b5bd22cb37c51b9dea424c9aa624a88b13` corrected both tests, preserved caller order for equal priorities, validated rule field/action types, handled absent category collections safely, and ranked preferred/wanted matches ahead of unmatched releases.
- Rerun / final outcome: the fix commit's complete Tests workflow passed (run [41722392894](https://github.com/SakibShahariar/aniyori/actions/runs/41722392894)).
- Remaining follow-up: none for this regression.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-03 | `f76856ba2b503ae5f443616f5a9f9597435a7b27` → `0a1f18b5bd22cb37c51b9dea424c9aa624a88b13` | Reviewed two commits: initial test defect red, correction green. |


## Reviewed range: 2026-11-03 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `97bf1b2f7be3ea57bbeeb669cb813d859cd0bdb1` | feat(gui): add smart release rule editor (#44) | green | [41722682388](https://github.com/SakibShahariar/aniyori/actions/runs/41722682388) |
| `2a39e57eec14278e5282f5ee80368d5d181b7b4c` | feat(gui): add smart release rule editor (#44) | green | [41722739710](https://github.com/SakibShahariar/aniyori/actions/runs/41722739710) |

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-03 | `0a1f18b5bd22cb37c51b9dea424c9aa624a88b13` → `2a39e57eec14278e5282f5ee80368d5d181b7b4c` | Reviewed two UI commits; both CI green. |


## Reviewed range: 2026-11-04

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `ebbd976f956360ed25a5661c5a829abbb1fdcc71` | feat(download): open selected Nyaa releases via magnet (#45) | green | [41722953410](https://github.com/SakibShahariar/aniyori/actions/runs/41722953410) |
| `f01f92e99a6e29dc79e18e246a3277a2c030d875` | feat(download): add qBittorrent Web API client (#45) | green | [41724280859](https://github.com/SakibShahariar/aniyori/actions/runs/41724280859) |
| `31bbff8a20990c7066202cb68daa066f39bc9c42` | fix(download): set qBittorrent multipart content type (#45) | green | [41724360774](https://github.com/SakibShahariar/aniyori/actions/runs/41724360774) |
| `8ccf10a227851f2fdd9bbcca32e2b4e8fa31d397` | fix(download): handle modern qBittorrent add responses (#45) | green | [41724467821](https://github.com/SakibShahariar/aniyori/actions/runs/41724467821) |

### qBittorrent client implementation notes

- Added a standard-library-only Web API client with cookie-based login, explicit torrent submission, category and paused options, and logout.
- Validates magnet v1 info hashes and server URLs. Cleartext HTTP is limited to loopback; remote WebUI endpoints require HTTPS. Redirects are rejected so credentials/cookies are not forwarded to another origin.
- Handles the legacy `Ok.` response and newer JSON success/pending counters.
- Passwords are supplied only to the client instance and are not persisted by the API client. The GTK configuration UI and Secret Service integration were completed in subsequent commits.
- Every commit in this reviewed range completed its Tests workflow successfully. No red runs were observed for these commits.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `2a39e57eec14278e5282f5ee80368d5d181b7b4c` → `8ccf10a227851f2fdd9bbcca32e2b4e8fa31d397` | Reviewed three commits; all three Tests workflows green. |


| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `43c2eb0dc822857816cdb08293a7beaa96ae3846` | feat(security): add Secret Service credential storage (#63) | green | [41724618766](https://github.com/SakibShahariar/aniyori/actions/runs/41724618766) |
| `c47b9ccfa08461693df461c8806886f93b9c1f99` | fix(security): distinguish missing secrets from keyring errors (#63) | green | [41724673662](https://github.com/SakibShahariar/aniyori/actions/runs/41724673662) |

### Credential-store implementation notes

- Added a Secret Service adapter using `secret-tool`; it sends secrets over stdin, supports lookup/removal, and fails closed if the helper/keyring is unavailable.
- No plaintext or custom cryptographic fallback was added. Encrypted fallback and live desktop keyring validation remain open work under #63.
- Both commits passed the complete Tests workflow.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `8ccf10a227851f2fdd9bbcca32e2b4e8fa31d397` → `c47b9ccfa08461693df461c8806886f93b9c1f99` | Reviewed two credential-storage commits; both Tests workflows green. |


## Failure investigation: qBittorrent settings serialization

- Commit SHA: `1c94b662579efebae3313ef8c1c1a8ced674e34d`
- Workflow / run: [Tests / 41724885784](https://github.com/SakibShahariar/aniyori/actions/runs/41724885784)
- Failed test: `test_round_trip_persists_only_non_secret_preferences_with_private_mode`.
- Diagnosis: the settings writer appended the two literal characters `\\n` instead of a newline, leaving invalid trailing data after the JSON document. Python compilation passed; the settings round-trip test caught the serialization defect.
- Classification: implementation defect in the new settings-store change.
- Fix: commit `20972d73fb4f63c7a2b631ed65c9fdd4b28b2437` corrects the serialized trailing newline and asserts the file ends with a real newline before reloading.
- Fix CI: the complete Tests workflow passed (run [41725019740](https://github.com/SakibShahariar/aniyori/actions/runs/41725019740)).


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `1c94b662579efebae3313ef8c1c1a8ced674e34d` | feat(download): persist qBittorrent connection settings (#45) | red | [41724885784](https://github.com/SakibShahariar/aniyori/actions/runs/41724885784) |
| `20972d73fb4f63c7a2b631ed65c9fdd4b28b2437` | fix(download): write valid qBittorrent settings JSON (#45) | green | [41725019740](https://github.com/SakibShahariar/aniyori/actions/runs/41725019740) |
| `afdd14713429707cda05001c00e1a8f600d7c25b` | feat(gui): configure and submit releases to qBittorrent (#45) | green | [41725336847](https://github.com/SakibShahariar/aniyori/actions/runs/41725336847) |

### Failure investigation: qBittorrent settings serialization

- Commit SHA: `1c94b662579efebae3313ef8c1c1a8ced674e34d`
- Workflow / run: [Tests / 41724885784](https://github.com/SakibShahariar/aniyori/actions/runs/41724885784)
- Failed test: `test_round_trip_persists_only_non_secret_preferences_with_private_mode`.
- Diagnosis: the writer appended the two literal characters `\\n` instead of a newline, leaving invalid trailing data after the JSON document. Compilation passed; the settings round-trip test caught the defect.
- Fix commit: `20972d73fb4f63c7a2b631ed65c9fdd4b28b2437`; the complete Tests workflow passed (run [41725019740](https://github.com/SakibShahariar/aniyori/actions/runs/41725019740)).
- Follow-up UI commit: `afdd14713429707cda05001c00e1a8f600d7c25b`; the complete Tests workflow passed (run [41725336847](https://github.com/SakibShahariar/aniyori/actions/runs/41725336847)).
- Remaining follow-up: real desktop/keyring/qBittorrent validation remains tracked in #45 and #63.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `c47b9ccfa08461693df461c8806886f93b9c1f99` → `afdd14713429707cda05001c00e1a8f600d7c25b` | Reviewed three commits: settings JSON regression red, serialization fix green, GTK qBittorrent integration green. |


| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `632b7958e1194ff0d322822920d99be60d3d250f` | docs: document qBittorrent release handoff (#45) | green | [41725508709](https://github.com/SakibShahariar/aniyori/actions/runs/41725508709) |

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `afdd14713429707cda05001c00e1a8f600d7c25b` → `632b7958e1194ff0d322822920d99be60d3d250f` | README now documents the qBittorrent API flow, Secret Service requirement, local settings path, and credential-removal behavior; CI green. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `cbdc9294150ea517cad3e4e546a48232733cefbd` | feat(search): add torrent search history controls (#64) | green | [41765361128](https://github.com/SakibShahariar/aniyori/actions/runs/41765361128) |

The torrent search-history UI was added to the Nyaa feed manager. The complete Tests workflow completed successfully; its unit-tests job passed compilation and the test suite.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `632b7958e1194ff0d322822920d99be60d3d250f` → `cbdc9294150ea517cad3e4e546a48232733cefbd` | Reviewed the new torrent-history UI commit; complete Tests workflow green. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `da530187558d73b1418eef684955021e29aef333` | test(search): verify private history file permissions (#64) | green | [41765533987](https://github.com/SakibShahariar/aniyori/actions/runs/41765533987) |

The search-history regression test confirms that the persisted history file is created with owner-only permissions (0600). The complete Tests workflow passed, including source compilation and unit tests.

- Reviewed checkpoint: `da530187558d73b1418eef684955021e29aef333`
- Commits after the previous checkpoint through this SHA: `cbdc9294150ea517cad3e4e546a48232733cefbd`, `da530187558d73b1418eef684955021e29aef333`; both completed green.


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `1f0323743e46753f6df04429d7ce13a7a0e0f957` | docs: clarify qBittorrent credential handling (#63) | green | [41725603725](https://github.com/SakibShahariar/aniyori/actions/runs/41725603725) |
| `92bb1f608b391b944c7a212d2de75ca0c9fcbe6b` | fix(security): remove superseded qBittorrent credentials (#63) | green | [41765630641](https://github.com/SakibShahariar/aniyori/actions/runs/41765630641) |

Both runs completed successfully. The unit-tests job passed Python source compilation and the complete unittest suite.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `da530187558d73b1418eef684955021e29aef333` → `92bb1f608b391b944c7a212d2de75ca0c9fcbe6b` | Reviewed the two omitted commits; both completed green. Checkpoint advanced to the current branch tip. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `071d00a59c02c75bdf39780660f88e3a4932c014` | feat(links): add configurable external anime links (#59) | green | [41766278479](https://github.com/SakibShahariar/aniyori/actions/runs/41766278479) |

The complete Tests workflow passed. The unit-tests job completed source compilation and the full unittest suite successfully.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `92bb1f608b391b944c7a212d2de75ca0c9fcbe6b` → `071d00a59c02c75bdf39780660f88e3a4932c014` | Reviewed the external-links implementation commit; CI green. Checkpoint advanced to this commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `12bb8b59932ecfa318b7ab81660336822c321904` | feat(backup): add full local backup and restore (#46) | green | [41766579077](https://github.com/SakibShahariar/aniyori/actions/runs/41766579077) |

The complete Tests workflow passed. Its unit-tests job completed Python source compilation and the full unittest suite successfully.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `071d00a59c02c75bdf39780660f88e3a4932c014` → `12bb8b59932ecfa318b7ab81660336822c321904` | Reviewed the full backup/restore implementation commit; CI green. Checkpoint advanced to this commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `27e21bb294823d796f4d41c6d88595bc7942716a` | feat(recognition): add configurable media exclusions (#52) | green | [41766947443](https://github.com/SakibShahariar/aniyori/actions/runs/41766947443) |

The complete Tests workflow passed. The unit-tests job completed Python source compilation and the full unittest suite successfully.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `12bb8b59932ecfa318b7ab81660336822c321904` → `27e21bb294823d796f4d41c6d88595bc7942716a` | Reviewed the recognition-exclusions implementation; CI green. Checkpoint advanced to this commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `4addcca6b73c8aa952de0b02ea58aeefe4e01715` | fix(recognition): skip matching excluded media (#52) | green | [41767034670](https://github.com/SakibShahariar/aniyori/actions/runs/41767034670) |

The complete Tests workflow passed. Python source compilation and the full unittest suite completed successfully.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `27e21bb294823d796f4d41c6d88595bc7942716a` → `4addcca6b73c8aa952de0b02ea58aeefe4e01715` | Reviewed the recognition short-circuit correction; CI green. Checkpoint advanced to this commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `482e3408ebce4d91ca833f8a41051c0dad079aa9` | feat(gui): support editing recognition exclusions (#52) | green | [41767133203](https://github.com/SakibShahariar/aniyori/actions/runs/41767133203) |

The complete Tests workflow passed. Python source compilation and the full unittest suite completed successfully.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `4addcca6b73c8aa952de0b02ea58aeefe4e01715` → `482e3408ebce4d91ca833f8a41051c0dad079aa9` | Reviewed the exclusion-management UI commit; CI green. Checkpoint advanced to this commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `f025df42fb15b2b8b332ecbaed3a74832907552c` | feat(history): add persistent watch-history log (#51) | green | [41767460396](https://github.com/SakibShahariar/aniyori/actions/runs/41767460396) |

The complete Tests workflow passed, including Python compilation and all unit tests.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `482e3408ebce4d91ca833f8a41051c0dad079aa9` → `f025df42fb15b2b8b332ecbaed3a74832907552c` | Reviewed the watch-history schema, storage, and UI implementation; CI green. Checkpoint advanced to this commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `886c7bc3666eb0b9d40d9fe4f60112c82dda340f` | fix(history): classify single-episode progress events (#51) | red | [41767554362](https://github.com/SakibShahariar/aniyori/actions/runs/41767554362) |

The unit-tests job failed one assertion in `test_history_can_be_filtered_by_anime_action_and_date`: the test inserted both the new automatic single-episode progress event and a second explicit episode event, then incorrectly expected only one result. Source compilation passed; the failing assertion is being corrected in the next commit.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `f025df42fb15b2b8b332ecbaed3a74832907552c` → `886c7bc3666eb0b9d40d9fe4f60112c82dda340f` | Reviewed the new single-episode event classification; CI exposed one incorrect test expectation. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `be7a4856601693d0c34c54c9d6c6b0d9b142667b` | test(history): isolate episode event filter assertion (#51) | green | [41767636544](https://github.com/SakibShahariar/aniyori/actions/runs/41767636544) |

The complete Tests workflow passed, including Python source compilation and all unit tests. The prior failed test assertion is corrected; the preceding red run remains recorded above.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `886c7bc3666eb0b9d40d9fe4f60112c82dda340f` → `be7a4856601693d0c34c54c9d6c6b0d9b142667b` | Reviewed the watch-history test correction; CI green after the recorded red run. Checkpoint advanced. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `f72b7b89df607a68d2e2b112166b3ba4dc14e794` | feat(download): add per-anime release preferences (#57) | red | [41768024350](https://github.com/SakibShahariar/aniyori/actions/runs/41768024350) |

The unit-tests job failed during Python source compilation in `aniyori/window.py`: the per-anime preference store load was accidentally inserted inside the release-rule editor's `try` block with invalid indentation. Unit tests were skipped. The next commit moves the load into the release-feed refresh setup.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `be7a4856601693d0c34c54c9d6c6b0d9b142667b` → `f72b7b89df607a68d2e2b112166b3ba4dc14e794` | Reviewed the initial per-anime preference integration; compile error recorded for correction. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `427f5ad1952d4490cce07cc3e72624a2712cdb4f` | fix(gui): load anime overrides during feed refresh (#57) | green | [41768156324](https://github.com/SakibShahariar/aniyori/actions/runs/41768156324) |

The complete Tests workflow passed, including source compilation and the full unittest suite. This corrects the compile failure recorded for the preceding implementation commit.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `f72b7b89df607a68d2e2b112166b3ba4dc14e794` → `427f5ad1952d4490cce07cc3e72624a2712cdb4f` | Reviewed the release-refresh load placement correction; CI green after the recorded red run. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `4e38f61fc67320c432852801b2dd39dbbc0f0220` | fix(download): enforce per-anime download eligibility (#57) | green | [41768256283](https://github.com/SakibShahariar/aniyori/actions/runs/41768256283) |

The complete Tests workflow passed, including source compilation and the full unittest suite.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `427f5ad1952d4490cce07cc3e72624a2712cdb4f` → `4e38f61fc67320c432852801b2dd39dbbc0f0220` | Reviewed per-anime eligibility enforcement; CI green. Checkpoint advanced to this commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `cde8823cb4cd740c37305d540dfb1e17f7ae0e3e` | feat(library): add sorting controls for list and grid views (#25) | red | [41768465125](https://github.com/SakibShahariar/aniyori/actions/runs/41768465125) |

The unit-tests job reported two failures: progress sorting placed entries with unknown episode totals ahead of known completion percentages, and the timestamp-map test regex was over-escaped. Source compilation passed. The correction places unknown-total entries after percentage-known entries and fixes the test pattern.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `4e38f61fc67320c432852801b2dd39dbbc0f0220` → `cde8823cb4cd740c37305d540dfb1e17f7ae0e3e` | Reviewed library sorting; two test failures recorded for correction. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `12ffcfc1ebc4e9373283a93a92d3d4e6b546d774` | fix(library): order unknown progress after known totals (#25) | green | [41768582095](https://github.com/SakibShahariar/aniyori/actions/runs/41768582095) |

The complete Tests workflow passed, including Python source compilation and the full unittest suite. This corrects the two test failures recorded for the initial library-sorting commit.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `cde8823cb4cd740c37305d540dfb1e17f7ae0e3e` → `12ffcfc1ebc4e9373283a93a92d3d4e6b546d774` | Reviewed the library sort correction; CI green after the recorded red run. |


## Reviewed range: 2026-11-04 (continued maintenance)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `ff8cbb1a6d4805137e2866408fbf6aeb1edf7df0` | feat(trailers): add AniList trailer playback action (#37) | green | [41768811099](https://github.com/SakibShahariar/aniyori/actions/runs/41768811099) |
| `a5a0ff8df6dbf5e00497f3ea155a7cf74226e113` | feat(storage): track watched state per episode (#24) | red | [41770763514](https://github.com/SakibShahariar/aniyori/actions/runs/41770763514) |
| `6cec42c3ecb5bdbcd1b64ea99aefe5e84ceabd8a` | fix(storage): distinguish episode rewatches in history (#24) | green | [41770881361](https://github.com/SakibShahariar/aniyori/actions/runs/41770881361) |
| `db78d80b0b1d4c5470485f9427bc7e47881b6460` | feat(webhooks): add secure configurable delivery service (#40) | green | [41773248196](https://github.com/SakibShahariar/aniyori/actions/runs/41773248196) |
| `5182258c44424fd345f2a5b082807ce6ca2268cf` | feat(gui): manage and dispatch watch webhooks (#40) | green | [41773497204](https://github.com/SakibShahariar/aniyori/actions/runs/41773497204) |
| `c283f151ee4c5abbb45772df998ffd0baec5e117` | fix(webhooks): notify bulk status changes and document privacy (#40) | green | [41773587399](https://github.com/SakibShahariar/aniyori/actions/runs/41773587399) |
| `a6a7b3c321b6331d7734ac356910d1bbc9159791` | feat(notifications): add persistent notification service (#48) | red | [41773825186](https://github.com/SakibShahariar/aniyori/actions/runs/41773825186) |

### Failure investigation: notification validation

- Failed job: `unit-tests`, test `test_rejects_invalid_preferences_and_notifications`.
- Diagnosis: `NotificationStore.add()` checked whether an event type was enabled before validating the event. An unknown type therefore returned `None` rather than raising `NotificationError`.
- Classification: validation-order bug in the new notification service.
- Correction: validate and normalize the notification before applying the user's event-type preference filter. The corrected commit and rerun are recorded in the next ledger entry.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `12ffcfc1ebc4e9373283a93a92d3d4e6b546d774` → `a6a7b3c321b6331d7734ac356910d1bbc9159791` | Reviewed all commits after the prior checkpoint, including the red runs and their corrective commits. Checkpoint advances after the correction is verified. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `de1e91738f90b407692d3ff62a4e3f7ea7edbe40` | fix(notifications): validate events before preference filtering (#48) | green | [41773942552](https://github.com/SakibShahariar/aniyori/actions/runs/41773942552) |
| `c457791cbea723506b5246865bfe9b4c3d4cbbea` | feat(gui): add notification center and event integrations (#48) | green | [41774077897](https://github.com/SakibShahariar/aniyori/actions/runs/41774077897) |

The initial notification service commit `a6a7b3c321b6331d7734ac356910d1bbc9159791` failed one test because disabled event preferences were checked before validating the event type (run [41773825186](https://github.com/SakibShahariar/aniyori/actions/runs/41773825186)). The validation-order fix is recorded above and passed the complete workflow. The notification UI/event integration commit also passed source compilation and the full test suite.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `a6a7b3c321b6331d7734ac356910d1bbc9159791` → `c457791cbea723506b5246865bfe9b4c3d4cbbea` | Reviewed notification service, its corrective commit, and UI/event integration. Checkpoint advanced to the green UI commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `7f7c0ad5dbd1fcd5d81bcd3ce471cb34274c544d` | feat(notifications): configure severity and deduplicate failures (#48) | red | [41774224552](https://github.com/SakibShahariar/aniyori/actions/runs/41774224552) |

### Failure investigation: notification severity test fixture

- Failed test: `test_preferences_filter_event_types_and_round_trip`.
- Diagnosis: the test fixture was changed to set the minimum severity to `warning`, while the same test still expected an `info` backup notification to be stored. The implementation correctly filtered it.
- Classification: inconsistent test expectation, not a product-code regression.
- Correction: restore the event-filter test's default `info` threshold; the separate severity-threshold test covers filtering.



## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `e4d72e64c9993a9707c45cb9bfaae8ba54a14616` | feat(network): add shared proxy and request settings (#62) | green | [41774614134](https://github.com/SakibShahariar/aniyori/actions/runs/41774614134) |
| `e4be1a144e0455fe9d08acd4f477ca0d1cc4603e` | feat(network): apply proxy and retry settings to service clients (#62) | red | [41774848525](https://github.com/SakibShahariar/aniyori/actions/runs/41774848525) |

### Failure investigation: cover-cache test patch target

- Four cover-cache tests failed during mock setup because the service now constructs its opener through `build_network_opener`, while the tests still patched the removed `build_opener` symbol.
- Source compilation passed; the failures were stale test patch targets caused by the integration refactor.
- Correction: update the cover-cache tests to patch the shared network-opener factory. The same integration batch also routes webhook requests through configured proxy/TLS/timeout settings.
- Retry and final outcome will be recorded after the next CI run.



## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `2ddfd825dc92e83e05f86cc58464077d4c6f5513` | test(notifications): align preference test with severity threshold (#48) | green | [41774324407](https://github.com/SakibShahariar/aniyori/actions/runs/41774324407) |
| `e4d72e64c9993a9707c45cb9bfaae8ba54a14616` | feat(network): add shared proxy and request settings (#62) | green | [41774614134](https://github.com/SakibShahariar/aniyori/actions/runs/41774614134) |
| `e4be1a144e0455fe9d08acd4f477ca0d1cc4603e` | feat(network): apply proxy and retry settings to service clients (#62) | red | [41774848525](https://github.com/SakibShahariar/aniyori/actions/runs/41774848525) |
| `a14281850f9f77266a92cf65ab7f0dda15a0598c` | fix(network): update cover tests and proxy webhook requests (#62) | green | [41775034660](https://github.com/SakibShahariar/aniyori/actions/runs/41775034660) |

The cover-cache test patch-target failure in `e4be1a1` was corrected in `a142818`; the complete Tests workflow passed, including Python compilation and all unit tests. The network integration now covers AniList, RSS, cover retrieval, webhook delivery, and qBittorrent requests. Only explicitly safe read-only requests retry; side-effecting POSTs do not.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `c457791cbea723506b5246865bfe9b4c3d4cbbea` → `a14281850f9f77266a92cf65ab7f0dda15a0598c` | Reviewed notification severity fix and all network-settings commits, including the red cover-test run and green correction. Checkpoint advanced to the verified green commit. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `24b34b065fd1980d110d59199d6001bf4efe4461` | test(network): verify proxy and timeout application (#62) | red | [41775168741](https://github.com/SakibShahariar/aniyori/actions/runs/41775168741) |

### Failure investigation: HTTPS handler test attribute

- Failed test: `test_opener_applies_proxy_and_keeps_tls_verification_enabled`.
- Diagnosis: the test inspected `HTTPSHandler.context`, but Python's urllib implementation stores the supplied SSL context as the private `_context` attribute. The opener construction itself succeeded.
- Classification: test introspection used the wrong stdlib attribute.
- Correction: assert against `HTTPSHandler._context`; TLS verification remains enabled because the implementation constructs the context with `ssl.create_default_context()`.



## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `b7ade8b6cb426987ee835468d8500be567d3d0a8` | test(network): inspect urllib TLS context correctly (#62) | green | [41775274127](https://github.com/SakibShahariar/aniyori/actions/runs/41775274127) |
| `c402a39346d4a54d6597dfb606c3281db22cc5e9` | feat(profiles): add portable storage and profile registry (#60) | red | [41775659452](https://github.com/SakibShahariar/aniyori/actions/runs/41775659452) |

### Failure investigation: profile context and injected environment

- Failed tests: default/named profile context display and profile-directory removal.
- Diagnosis: the tests compared the active profile ID to the display name, and `ProfileStore.remove()` read process-global `os.environ` instead of the environment mapping supplied to `configure_storage_environment()`.
- Classification: context field expectation and environment-injection consistency bugs.
- Correction: tests now assert `active_name`; `ProfileStore` retains the supplied environment mapping for path cleanup, and the bootstrap passes that mapping through.



## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `b7ade8b6cb426987ee835468d8500be567d3d0a8` | test(network): inspect urllib TLS context correctly (#62) | green | [41775274127](https://github.com/SakibShahariar/aniyori/actions/runs/41775274127) |
| `c402a39346d4a54d6597dfb606c3281db22cc5e9` | feat(profiles): add portable storage and profile registry (#60) | red | [41775659452](https://github.com/SakibShahariar/aniyori/actions/runs/41775659452) |
| `e9cd189a25d03f793d905db42d0e9e64869c46d4` | fix(profiles): honor configured environment during profile cleanup (#60) | green | [41775820202](https://github.com/SakibShahariar/aniyori/actions/runs/41775820202) |
| `2d5534c550a12c65995e131c6ff8b9bce7619546` | feat(gui): manage isolated profiles and portable mode (#60) | green | [41775934373](https://github.com/SakibShahariar/aniyori/actions/runs/41775934373) |

The initial profile service run exposed three test failures: two compared profile IDs with display names, and one showed that cleanup used process-global environment values rather than the injected environment. The correction aligned the assertions and made the store retain its environment mapping. The full workflow passed after the correction and again after the GTK profile manager/bootstrap integration.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-04 | `a14281850f9f77266a92cf65ab7f0dda15a0598c` → `2d5534c550a12c65995e131c6ff8b9bce7619546` | Reviewed the final network test, profile storage/service, correction, and profile UI/bootstrap commits; all final outcomes green. Checkpoint advanced. |


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `1dd84fd30c80fc1fde6d980bfe10592fc33e75ab` | fix(profiles): guard active profile removal and document migration (#60) | green | [41776092223](https://github.com/SakibShahariar/aniyori/actions/runs/41776092223) |
| `0198ea4cdc3f3aaae9cbcb8779aa441c618caee0` | feat(library): add persisted per-view layout preferences (#65) | green | [41776342777](https://github.com/SakibShahariar/aniyori/actions/runs/41776342777) |

The profile-removal guard and migration documentation passed the complete Tests workflow. The library-layout commit also passed compilation and unit tests; review confirmed that it adds only the persistence service and tests, not GTK integration. Issue #65 therefore remains open as Category B until the preferences are connected to the list/grid widgets and desktop usability is checked.


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `cd22acb15db9af586f3f75989edce3bbd7fa89c5` | feat(history): add individual episode editor (#24) | green | [41789546031](https://github.com/SakibShahariar/aniyori/actions/runs/41789546031) |

The episode editor is wired into both list and grid cards. The workflow compiled all Python sources and completed the unit-test suite successfully. Issue #24 remains open solely for live GTK interaction validation.


## Reviewed range: 2026-11-04 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `966f82c4b65102486cc585494d2e86c5f7f83d55` | test(backup): cover watch history restoration (#46) | green | [41791140752](https://github.com/SakibShahariar/aniyori/actions/runs/41791140752) |

The backup round-trip now exercises Aniyori's real `LibraryStorage` schema and watch-history API rather than a synthetic table. It records an event before backup, adds another afterward, restores, and verifies only the original event is present.


## Reviewed range: 2026-11-06

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `816622bac5bfa6745eebbc0fd1101cee9d9f043e` | feat(discovery): add interactive seasonal anime charts (#36) | green | [42156887488](https://github.com/SakibShahariar/aniyori/actions/runs/42156887488) |
| `4642fc335559b76a99503dc782a8acacc6fcde63` | test(discovery): register seasonal client tests (#36) | green | [42156934229](https://github.com/SakibShahariar/aniyori/actions/runs/42156934229) |

The first implementation commit passed compilation and the then-current test suite, but review found that the newly appended seasonal client tests were below the module's direct test-runner guard and therefore were not discovered by unittest. The follow-up commit moved those tests into the existing test class before the guard. The follow-up Tests workflow passed with the tests registered. Both commits have observed green workflow results; the test-discovery caveat is preserved here rather than treating the first green run as evidence that those new tests had executed.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-06 | `966f82c4b65102486cc585494d2e86c5f7f83d55` → `4642fc335559b76a99503dc782a8acacc6fcde63` | Reviewed seasonal discovery implementation and test-registration correction; both workflow runs completed green. |


## Reviewed range: 2026-11-04 to 2026-11-06 (checkpoint reconciliation)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `833c9900d0a3f9bf59c8ec7fbe6e4cd53e7915c4` | test(backup): verify real watch history round trip (#46) | green | [41791369006](https://github.com/SakibShahariar/aniyori/actions/runs/41791369006) |
| `792f6028818e4a40785c7ced4b493be976c74c38` | docs(agents): clarify acceptance criteria evidence | green | [41864277025](https://github.com/SakibShahariar/aniyori/actions/runs/41864277025) |
| `816622bac5bfa6745eebbc0fd1101cee9d9f043e` | feat(discovery): add interactive seasonal anime charts (#36) | green | [42156887488](https://github.com/SakibShahariar/aniyori/actions/runs/42156887488) |
| `4642fc335559b76a99503dc782a8acacc6fcde63` | test(discovery): register seasonal client tests (#36) | green | [42156934229](https://github.com/SakibShahariar/aniyori/actions/runs/42156934229) |
| `851b137ee55317a224e6bee073fdf1636bda8c62` | docs(discovery): document seasonal charts and CI audit (#36) | green | [42157071212](https://github.com/SakibShahariar/aniyori/actions/runs/42157071212) |

The backup round-trip and agent-guidance commits were missing from the previous incremental table; their individual Tests runs were checked and are recorded above. The seasonal implementation, test-registration correction, and feature documentation commits also completed the Tests workflow successfully. The first seasonal implementation run did not discover the newly added client tests; this was corrected in the follow-up commit and is documented in the prior review entry.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-06 | `966f82c4b65102486cc585494d2e86c5f7f83d55` → `851b137ee55317a224e6bee073fdf1636bda8c62` | Reconciled the backup test and agent-guidance commits, then verified the seasonal feature, its test-registration correction, and documentation; all observed runs green. |


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `b3c8de3b6c0045c3d2d62b2c3db72f68349f04b2` | fix(discovery): bypass fresh cache on manual refresh (#36) | green | [42157258082](https://github.com/SakibShahariar/aniyori/actions/runs/42157258082) |
| `e661a006d27d10037d25b27236aefb48165bf3a3` | fix(discovery): sort by next airing date (#36) | green | [42157349605](https://github.com/SakibShahariar/aniyori/actions/runs/42157349605) |

The manual refresh action now bypasses a fresh season cache while changing to another season/year can still reuse cached data. The date sort uses AniList's next-airing timestamp when present and falls back to season start date. Both corrective commits passed the complete Tests workflow.

| Date | Reviewed range / checkpoint | Result summary |
|---|---|---|
| 2026-11-06 | `851b137ee55317a224e6bee073fdf1636bda8c62` → `e661a006d27d10037d25b27236aefb48165bf3a3` | Reviewed manual-refresh and next-airing-sort fixes; both Tests runs completed green. |


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `4720b267f04d45a1dae2c2c3074bead5c311535b` | docs(discovery): clarify airing-date and refresh behavior (#36) | green | [42157447377](https://github.com/SakibShahariar/aniyori/actions/runs/42157447377) |
| `d1eeb2671e11c2703ffcc47f7f9ae6f8c4cdb3fd` | feat(library): apply customizable list and grid layouts (#65) | green | [42164437656](https://github.com/SakibShahariar/aniyori/actions/runs/42164437656) |
| `bdf2e85c0a8b4ad97ab007db622adf9eb7b55f08` | fix(library): apply title width and progress visibility (#65) | green | [42164488854](https://github.com/SakibShahariar/aniyori/actions/runs/42164488854) |

The seasonal discovery documentation commit completed the Tests workflow successfully. The layout integration commit and its follow-up correction also completed source compilation and the full unit-test suite successfully. The UI preferences now feed the row/card widgets; live small-window and visual interaction validation remains open under #65.

- Reviewed checkpoint: `bdf2e85c0a8b4ad97ab007db622adf9eb7b55f08`
- Commits after the previous checkpoint through this SHA: `4720b267f04d45a1dae2c2c3074bead5c311535b`, `d1eeb2671e11c2703ffcc47f7f9ae6f8c4cdb3fd`, and `bdf2e85c0a8b4ad97ab007db622adf9eb7b55f08`; all three Tests runs completed green.


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `872858c54af13426a1803a7fd4b5a97d14270995` | docs(library): document layout preferences and CI audit (#65) | green | [42164649478](https://github.com/SakibShahariar/aniyori/actions/runs/42164649478) |
| `df3e3709562666f7677967faafb9a80b21c06f2c` | docs(release): prepare v0.1.0 draft notes (#81) | green | [42164750197](https://github.com/SakibShahariar/aniyori/actions/runs/42164750197) |
| `b173014cebe279e37cbbf9aa68de03edf080e93b` | feat(links): expose anime links in episode editor (#59) | green | [42164886022](https://github.com/SakibShahariar/aniyori/actions/runs/42164886022) |
| `4ae810f57b9d8756eb5f477525079f862d5b8a14` | feat(download): add qBittorrent queue API methods (#56) | green | [42165037594](https://github.com/SakibShahariar/aniyori/actions/runs/42165037594) |
| `43b746784847db19678c432ceb30704d4f4f04ec` | test(download): cover qBittorrent queue API actions (#56) | green | [42165072760](https://github.com/SakibShahariar/aniyori/actions/runs/42165072760) |
| `2dca1027a1bc59955d53056e6e32eeb15dd2bc91` | feat(gui): add qBittorrent download queue view (#56) | green | [42165153095](https://github.com/SakibShahariar/aniyori/actions/runs/42165153095) |
| `9345bb5b94d1361d032312b1d5a182a8a7b253e8` | fix(gui): keep qBittorrent queue refresh responsive (#56) | green | [42165184982](https://github.com/SakibShahariar/aniyori/actions/runs/42165184982) |
| `053c5e1333edecaed4e259effe89a1d2fa9a7d3a` | fix(download): support qBittorrent v5 queue controls (#56) | red — stale test expectation | [42165244536](https://github.com/SakibShahariar/aniyori/actions/runs/42165244536) |
| `c7c0879c5c4f178d05b99fc68cef1b06cddd0ea6` | test(download): cover qBittorrent v5 and legacy queue controls (#56) | green — corrected the test expectation and verified fallback | [42165273480](https://github.com/SakibShahariar/aniyori/actions/runs/42165273480) |
| `4ff22c25cd0f65d86a5cb8978055624a5c874656` | feat(gui): show per-torrent progress and transfer rates (#56) | green | [42165376615](https://github.com/SakibShahariar/aniyori/actions/runs/42165376615) |
| `f0bd8009873c4a183f91ca2254d1a5c79e1f053c` | feat(download): add torrent recheck recovery action (#56) | green | [42165451347](https://github.com/SakibShahariar/aniyori/actions/runs/42165451347) |
| `9000a890b07d2cf0d45953261700b051edf13862` | test(download): cover torrent recheck action (#56) | green | [42165471495](https://github.com/SakibShahariar/aniyori/actions/runs/42165471495) |
| `499dcd9d1e3330d4b058e17f65d877f771aa17e6` | feat(gui): add recovery action for failed torrents (#56) | green | [42165488219](https://github.com/SakibShahariar/aniyori/actions/runs/42165488219) |

The release-draft, layout documentation, and episode-editor link commits completed CI successfully. The queue implementation was built in small direct commits and every run was inspected. One compatibility commit initially failed because its test still expected the older endpoint names; the immediately following test commit updated the expectation and verified both qBittorrent 5.x and legacy fallback paths. The current queue implementation and recovery action both pass the full Tests workflow. No CI failure remains unresolved in this reviewed range.

- Reviewed checkpoint: `499dcd9d1e3330d4b058e17f65d877f771aa17e6`
- Commits after the previous checkpoint through this SHA: all commits listed in this table; the only red run is explicitly corrected by the succeeding green test commit.


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `1af5f6e0abadc0811336befe7fd8ada3da33ef81` | docs(download): document queue and reconcile CI audit (#56) | green | [42165626969](https://github.com/SakibShahariar/aniyori/actions/runs/42165626969) |
| `70a26a1e7827509d8d40f08d5d5528132c1c08ca` | fix(discovery): prune stale airing cache entries (#36) | green | [42165778682](https://github.com/SakibShahariar/aniyori/actions/runs/42165778682) |
| `8b54a4f2f3a87acd33e1952c30ac029b8b401a0a` | feat(discovery): include trailer metadata in search results (#37) | green | [42165843511](https://github.com/SakibShahariar/aniyori/actions/runs/42165843511) |
| `50ce377c2d7f6ff8c9dae9188a9dc776b9b93dec` | feat(discovery): add trailer actions to search and season views (#37) | green | [42165880901](https://github.com/SakibShahariar/aniyori/actions/runs/42165880901) |
| `d692c149603a159e2a0bde628383f9cd3e1ff429` | test(discovery): cover seasonal trailer metadata (#37) | green | [42165911143](https://github.com/SakibShahariar/aniyori/actions/runs/42165911143) |
| `d85e9aa7048fe86e28728048bf113d192a5f8596` | feat(discovery): add trailer action to anime editor (#37) | green | [42165946541](https://github.com/SakibShahariar/aniyori/actions/runs/42165946541) |
| `0700be008e716150d4df56224c36f128ffebaa7c` | test(discovery): verify trailer metadata queries (#37) | green | [42165966857](https://github.com/SakibShahariar/aniyori/actions/runs/42165966857) |

The queue documentation/audit commit passed CI. The stale-airing-cache correction and all trailer query/UI/test commits also passed the complete Tests workflow. Trailer metadata is now requested in search and seasonal queries, and actions are available from the edit dialog, catalogue review-details page, and seasonal cards. Live GTK/mpv/default-handler verification remains outstanding.

- Reviewed checkpoint: `0700be008e716150d4df56224c36f128ffebaa7c`
- Commits after the previous checkpoint through this SHA: all commits listed in this table; all seven Tests runs completed green.


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `f553c8abb19ae397ea6c60624c9d4be4d9d5b2f5` | docs(discovery): document trailer actions and CI audit (#37) | green | [42166137742](https://github.com/SakibShahariar/aniyori/actions/runs/42166137742) |

The trailer documentation and audit commit completed the Tests workflow successfully. This next release-documentation change records the actual minimum libadwaita API requirement: the application uses `Adw.AlertDialog`, which is available since libadwaita 1.5. The distribution commands are now scoped to current releases whose package repositories provide that API; the README launch command matches the repository's actual `main.py` entry point.

- Reviewed checkpoint: `f553c8abb19ae397ea6c60624c9d4be4d9d5b2f5`
- Commits after the previous checkpoint: `f553c8abb19ae397ea6c60624c9d4be4d9d5b2f5`; its Tests run completed green.


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `71fd58df47f51145900690ee5923a60b4faaad8b` | docs(release): clarify GTK runtime requirements (#81) | green | [42166377099](https://github.com/SakibShahariar/aniyori/actions/runs/42166377099) |

The release dependency review also confirmed that `Gtk.Picture.set_content_fit()` requires GTK 4.8. The README and draft changelog now state both actual API minimums: GTK 4.8+ and libadwaita 1.5+.

- Reviewed checkpoint: `71fd58df47f51145900690ee5923a60b4faaad8b`
- Commits after the previous checkpoint: `71fd58df47f51145900690ee5923a60b4faaad8b`; Tests completed green.


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `3afedcb8dab683ec92f5c85982ca144e831b8c71` | docs(release): specify GTK minimum version (#81) | green | [42166540463](https://github.com/SakibShahariar/aniyori/actions/runs/42166540463) |
| `b78993bed0db17b4aa92bc2250003e03795dca6d` | fix(library): reset list and grid layouts independently (#65) | green | [42166642882](https://github.com/SakibShahariar/aniyori/actions/runs/42166642882) |

The GTK minimum-version documentation commit and the independent per-view layout-reset correction both completed source compilation and the full unit-test suite successfully. Issue #65 remains open only for live visual and small-window interaction validation.

- Reviewed checkpoint: `b78993bed0db17b4aa92bc2250003e03795dca6d`
- Commits after the previous checkpoint: `3afedcb8dab683ec92f5c85982ca144e831b8c71` and `b78993bed0db17b4aa92bc2250003e03795dca6d`; both Tests runs completed green.


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `cffb134a2b46f1bd38057db70286401a04355d10` | docs(library): clarify independent layout resets and CI audit (#65) | green | [42166781641](https://github.com/SakibShahariar/aniyori/actions/runs/42166781641) |
| `b403130e9a41345899523ce98729598be4226d30` | docs(discovery): clarify trailer feature summary (#37) | green | [42170438423](https://github.com/SakibShahariar/aniyori/actions/runs/42170438423) |

The independent list/grid reset documentation and the trailer feature-summary correction both passed the complete Tests workflow. The README now describes the trailer actions without the earlier punctuation error.

- Reviewed checkpoint: `b403130e9a41345899523ce98729598be4226d30`
- Commits since the previous recorded checkpoint: `cffb134a2b46f1bd38057db70286401a04355d10` and `b403130e9a41345899523ce98729598be4226d30`; both Tests runs completed green.


## Incremental review: 2026-11-06

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| fc573209083f765474e55129ba8b9df03a5a58f9 | docs(maintenance): update commit CI audit | green | [42170595201](https://github.com/SakibShahariar/aniyori/actions/runs/42170595201) |
| a240267a020fd81ad80c50a35e7d3bf7cbc67506 | docs(qa): add live desktop validation checklist (#84) | green | [42170963371](https://github.com/SakibShahariar/aniyori/actions/runs/42170963371) |

Both commits completed the repository Tests workflow successfully. The reviewed range is advanced through the current default-branch checkpoint a240267a020fd81ad80c50a35e7d3bf7cbc67506; the next substantive commit will record its own completed check.


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| 3496728ecf956babf7425a82b8cf659a7c70f4a1 | feat(notifications): add opt-in airing reminders (#31) | green | [42173388953](https://github.com/SakibShahariar/aniyori/actions/runs/42173388953) |
| 18fc47973f5f886c88bc12fd06c4adf991d8f114 | feat(playback): add MPRIS recognition helpers (#32) | green | [42173686243](https://github.com/SakibShahariar/aniyori/actions/runs/42173686243) |
| 5ef314f16ff1979189bdc6db24d9843ad618b565 | test(playback): cover MPRIS recognition safeguards (#32) | green | [42173747712](https://github.com/SakibShahariar/aniyori/actions/runs/42173747712) |
| 81b821c5be0586cb710085d5deb5eb5785f8ea39 | feat(playback): connect mpv and VLC MPRIS tracking (#32) | green | [42173842483](https://github.com/SakibShahariar/aniyori/actions/runs/42173842483) |

The airing-reminder change, MPRIS helper and safeguards, and mpv/VLC GTK integration all completed the Tests workflow successfully. These checks cover compilation and unit tests; live mpv/VLC playback remains a manual desktop validation item under #32.


## Reviewed range: 2026-11-06 (continued)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| 2412b85e4a3730210fe36d60823e504491683054 | docs(playback): document opt-in player tracking and CI (#32) | green | [42174059051](https://github.com/SakibShahariar/aniyori/actions/runs/42174059051) |
| ccf526e01efc29c36d858609a6dcf5aa76475080 | perf(airing): batch AniList schedule refreshes (#31) | red — malformed-response test exposed that the offline fallback swallowed a data-validation error | [42174409355](https://github.com/SakibShahariar/aniyori/actions/runs/42174409355) |
| da53f0df294ae06fcadd56cd2a992b332a20cf8b | fix(airing): preserve malformed response errors (#31) | green — fallback now handles transport/API errors only; malformed payloads remain explicit errors | [42174549934](https://github.com/SakibShahariar/aniyori/actions/runs/42174549934) |

The initial batching commit exposed an error-path regression: malformed responses were treated like offline transport failures. The corrective commit separated the request failure fallback from response validation. The complete Tests workflow passed on the correction.
- Reviewed checkpoint: da53f0df294ae06fcadd56cd2a992b332a20cf8b


## Reviewed range: 2026-11-06 (continued — status evidence unavailable)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `525be792c442574f2aa0521a15567be8c90260b5` | docs(airing): document batched schedule refresh and CI (#31) | unavailable | — |
| `4a8185becf4c4be949e0034d38446f3c8b05ba54` | feat(history): add local yearly activity aggregation (#88) | unavailable | — |
| `ac7093bb1308f47532b1e2c5dc320cc95534d0d5` | test(history): cover yearly activity aggregation (#88) | unavailable | — |
| `1a6ca9d028c2ea91cd5fde90eab968e6dc217f57` | fix(history): validate yearly event inputs (#88) | unavailable | — |
| `342edd2b9742847c8dfd05d23f46aae3bb87269e` | perf(history): query insights by local calendar year (#88) | unavailable | — |
| `05a6c4d8c33a57b65986e87aa960fb9de4368795` | test(history): cover indexed local-year queries (#88) | unavailable | — |
| `5d4c3f09b56013a38202465f5e4bf30926af8685` | feat(gui): add yearly watch-history insights (#88) | unavailable | — |
| `a94f325de761c73d102662ca7b5c4384ae621e74` | fix(gui): count all monthly history activity (#88) | unavailable | — |
| `216d01522f25fa22114bdfbde6e84ba4dbe08467` | fix(gui): preserve statistics dialog line breaks (#88) | unavailable | — |
| `64bfe664ade920c9bc20f6b9d3c9df0ec40d0ba0` | perf(gui): calculate yearly history off the GTK thread (#88) | unavailable | — |
| `9a44239ea9502db1e8588cb7310e59deb9af476b` | fix(gui): correct statistics dialog newlines (#88) | unavailable | — |
| `14910a812fb1a305052c9a576681f593fb604921` | fix(history): harden malformed event handling (#88) | unavailable | — |
| `a08cad5988a1db004aef044042f0f9bff61dfbba` | style(gui): organize statistics imports (#88) | unavailable | — |
| `74d79bfe37460bd65caf906f9b32656ba0a98828` | style(history): clarify timezone typing (#88) | unavailable | — |
| `968978d74f7fc1ce32223eada62550ad81d08e98` | test(history): cover malformed duplicate events (#88) | unavailable | — |
| `71f5fd9bf58fbe3441745f7a5827b0488df16625` | docs(qa): add yearly history validation steps (#88) | unavailable | — |

The combined commit-status lookup returned an empty status list for every SHA above. The available workflow-run lookup only exposes pull-request-triggered runs, so it did not provide push-triggered Tests run details for this range. **Unavailable is not green or red**; no CI pass is claimed. Recheck these exact SHAs when the Tests workflow run metadata is accessible.

- Reviewed checkpoint: `71f5fd9bf58fbe3441745f7a5827b0488df16625`


## Reviewed range: 2026-11-06 (continued — status evidence unavailable)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `7bf81b4f462a904e28f35a930ba98bf3aa97be03` | docs(maintenance): record unavailable CI evidence for history insights | unavailable | — |
| `703392334d7ec23718354fd0a7b557922677907f` | docs(readme): mention yearly watch-history insights (#88) | unavailable | — |
| `b01e686a43cc4d7c94ade4cb24ec87875f1ddeef` | feat(scanner): report file sizes and unavailable roots (#87) | unavailable | — |
| `1f10d64d116e1bbce6765cad01f6e9c01b04d573` | feat(scanner): propagate scan completeness and sizes (#87) | unavailable | — |
| `203aba13fffebc88a295829b8eeee9cca5a43b64` | feat(scanner): add per-anime size and next-unwatched data (#87) | unavailable | — |
| `03676b863f4506d07aac9b08ea9cd010b66625d2` | feat(scanner): expose partial scan and collection totals (#87) | unavailable | — |
| `2299390e233cb3231c0e4f0ce58de6066eea6515` | test(scanner): cover local size and unwatched selection (#87) | unavailable | — |
| `65d235792956abf13875c37a24863d71023c9244` | test(scanner): cover unavailable roots and size safety (#87) | unavailable | — |
| `0be911bb14e6f74812c9a39e5c529bf96e08d2f7` | test(scanner): cover aggregate and partial scan results (#87) | unavailable | — |
| `f174c2db0abca9c34f265698147a7c9cd5d5565d` | fix(scanner): snapshot configured roots before scanning (#87) | unavailable | — |
| `3ead6e0fc0e3f419a729f81cb2f5b3b303e1490b` | feat(gui): show local collection insights and folder actions (#87) | unavailable | — |
| `0137196c01949df1aeece73c22f85a4321dde3b1` | test(scanner): verify recognition size metadata (#87) | unavailable | — |
| `ee4d45f4e57a68f9de56abf53b16b71bc170f828` | test(scanner): cover unreadable files and broken links (#87) | unavailable | — |
| `fc0aa5e6fdf52db29c8af75ca031b316e00b9230` | docs(qa): add local collection validation steps (#87) | unavailable | — |
| `a45f118839f04159ffb3d4f80cc9f2632aa4ab24` | fix(scanner): deduplicate hard links by file identity (#87) | unavailable | — |
| `2715298649ea57d358f86abe63f37ed4005606c3` | test(scanner): count hard-linked files once (#87) | unavailable | — |
| `c19f88f357b06b4361c95c715a6788b979e08c2f` | fix(gui): clarify unique file size totals (#87) | unavailable | — |
| `a003c28dba802c4b8b86d855fad721238a90e02b` | fix(scanner): accept numeric watched-state keys (#87) | unavailable | — |
| `ca6984728998291507cfd4b99590c43173665e93` | fix(scanner): preserve hard-link paths while deduplicating size (#87) | unavailable | — |
| `cce1d5bc5f0318322b64bb768d53349dce12f94f` | fix(scanner): carry stable file identity through recognition (#87) | unavailable | — |
| `c81bedccdb183b7e9df60f3a766a02e4e5b14c36` | fix(scanner): avoid duplicate hard-link anime sizes (#87) | unavailable | — |
| `bf934ca185fdd318ac4a63e04e67e479e6f7b43b` | test(scanner): distinguish paths from unique file size (#87) | unavailable | — |
| `e725a2aa90b3257f321f9c5856b589a6317ec3f6` | test(scanner): deduplicate per-anime hard-link sizes (#87) | unavailable | — |
| `56f0e450cb3eed17bc5f09f3edcbc72dc07356d3` | docs(qa): align hard-link size validation (#87) | unavailable | — |

The combined commit-status lookup returned an empty status list for every SHA above. Push-triggered Tests run details were not available through the connected workflow-run surface. These entries are **unavailable**, not assumed green or red; recheck the exact SHAs when Actions run metadata is accessible.

- Reviewed checkpoint: `56f0e450cb3eed17bc5f09f3edcbc72dc07356d3`


## Reviewed range: 2026-11-06 (continued — status evidence unavailable)

| Commit SHA | Subject | CI result | Run |
|---|---|---|---|
| `779ea9e33b1e95b3159b0ef44f64ac0eea5fc327` | docs(maintenance): record scanner CI evidence availability | unavailable | — |
| `1d6fd1334c5a64461ab345135b721eab456f5414` | docs(scanner): clarify hard-link path and size behavior (#87) | unavailable | — |
| `c62de432d8f50e187c0b7c77061b96f94d7a8302` | fix(gui): distinguish unknown and absent unwatched episodes (#87) | unavailable | — |
| `bd15a99b415ab767133c695e82df8e8d1ab62341` | test(scanner): cover root escape and symlink loops (#87) | unavailable | — |
| `281ed87481c76525e6d679920d694dd678dc3935` | test(scanner): preserve configured root snapshots (#87) | unavailable | — |
| `37e5ffb3bef29218b1d19da8b47fa350c424c1ff` | docs(scanner): clarify path-based scanner return values (#87) | unavailable | — |
| `e969fc2113150141d897c3771e9452b29ec3dad0` | fix(gui): label unknown-total episode estimates accurately (#87) | unavailable | — |
| `76680402a49e43ed02c6f5787b153f7f804b4cfd` | feat(gui): explain unclassified local media paths (#87) | unavailable | — |
| `bcdbc1c9b0e43e3f6acbd4588b162bd102a15f48` | docs(gui): qualify inode-based size deduplication (#87) | unavailable | — |
| `084c6d6ce123ae324770481e19d3bbd642790010` | docs(qa): qualify inode-based size deduplication (#87) | unavailable | — |
| `b7d00a9cdba5094aceec45a3491ea51051b3d7bd` | feat(library): add validated named view preset storage (#89) | unavailable | — |
| `6812b87a834f5071da8d5c3545121df4a3ba0a84` | fix(library): tolerate malformed preset option values (#89) | unavailable | — |
| `54f5f79125cc76a5e755e7289b29231072a77f33` | test(library): cover named view preset storage (#89) | unavailable | — |
| `64b4193ce21290264128660344a1eb5231f6dfd3` | feat(library): support updating saved view presets (#89) | unavailable | — |
| `7c3a993b888b71334f3f9b65a61962616ed07fc2` | test(library): cover updating named view presets (#89) | unavailable | — |
| `77017f197bcd4a8087bd05ba5e7eece7e73fa2df` | feat(gui): manage named library-view presets (#89) | unavailable | — |
| `c2acf853737848fb92a4cb9447bc42c1e4f544ac` | fix(gui): harden preset selection and default handling (#89) | unavailable | — |
| `e0f629fbfc46063fad2e0e77eff0ddfbac549371` | test(library): cover list/grid presets and layout isolation (#89) | unavailable | — |
| `2f52d6246d935de027e1388fcad77b6b6c57c7f3` | docs(qa): add library-view preset validation steps (#89) | unavailable | — |
| `272007b61d975ab92f8c33193b2df31ad3bf4574` | fix(library): preserve oversized preset files safely (#89) | unavailable | — |
| `7db3ea3c8c82f1d6f2ce4ef4bf40054d5c97244c` | test(library): protect oversized preset data (#89) | unavailable | — |
| `b9918624c8129594634910b8c80204f6169d3eb0` | docs(readme): document view presets and local collection insights (#87 #89) | unavailable | — |
| `25b1d56cc8b6ea88bdffae22e18c3b8e5c66db79` | fix(scanner): avoid false episode counts for hard-link aliases (#87) | unavailable | — |
| `3d8381ace000c8ea987de1af9facf38b05410ca6` | test(scanner): withhold conflicting hard-link episode assignments (#87) | unavailable | — |
| `442e9e376ed851e1ad10e87a821fbb93dc0eda24` | fix(gui): explain conflicting hard-link episode names (#87) | unavailable | — |
| `4de5dc4ad873389a8e0d0c64f803fa873e90d79a` | docs(qa): cover conflicting hard-link episode names (#87) | unavailable | — |
| `d710b49e47dbc7d9bd16dd691a161be18c1f2112` | fix(library): tolerate malformed preset layouts (#89) | unavailable | — |
| `8dc45abef98ad16ad40e005c7438ab0f80ba76e7` | test(library): cover malformed nested preset layouts (#89) | unavailable | — |
| `13a833c803d560f37db7b1808f1667307b34b77c` | docs(gui): clarify preset scope (#89) | unavailable | — |

The combined commit-status lookup returned an empty status list for every SHA above. No push-triggered Tests run details were exposed by the connected workflow-run surface. These entries are **unavailable**, not assumed green or red. Recheck these exact SHAs when Actions run metadata is accessible.

- Reviewed checkpoint: `13a833c803d560f37db7b1808f1667307b34b77c`

## Reviewed range: 2026-11-15 — AniList account integration (#22)

Reviewed the 24 commits after checkpoint `13a833c803d560f37db7b1808f1667307b34b77c` through `d2c7064940b80a24442e4cca183b934477976eea`. Every commit has an observed completed-success GitHub Actions Tests run. The combined-status endpoint returned empty status lists; the push-triggered workflow-run records below are the evidence used for the green classifications.

| Commit SHA | Subject | CI result | Workflow run |
|---|---|---|---|
| `a87ef1f269cdb39b3cc9d69566139d40abca90bb` | feat(anilist): add desktop OAuth account helpers (#22) | green | [43699199565](https://github.com/SakibShahariar/aniyori/actions/runs/43699199565) |
| `970b42a8f4df52116e3d54fdf03d17c2b8ee6197` | test(anilist): cover desktop OAuth helpers (#22) | green | [43699212965](https://github.com/SakibShahariar/aniyori/actions/runs/43699212965) |
| `5d254d033222f7652e7e04f87141ad98a033b34b` | feat(anilist): add authenticated library API support (#22) | green | [43699231326](https://github.com/SakibShahariar/aniyori/actions/runs/43699231326) |
| `81ef8eb8150fabd97dd69168cba695bb2d5a3437` | test(anilist): cover authenticated library operations (#22) | green | [43699251785](https://github.com/SakibShahariar/aniyori/actions/runs/43699251785) |
| `bd3730f5346fa2319112099ef763924567112ea2` | fix(anilist): reject malformed list status values (#22) | green | [43699258790](https://github.com/SakibShahariar/aniyori/actions/runs/43699258790) |
| `6da2cc9a3a08595a758db40cdf693ac03ba3660f` | feat(anilist): add account connection and import dialog (#22) | green | [43699293660](https://github.com/SakibShahariar/aniyori/actions/runs/43699293660) |
| `361f6c1861a4d45c6a6c6c3f2042690c02863139` | feat(anilist): expose account integration in app menu (#22) | green | [43699306774](https://github.com/SakibShahariar/aniyori/actions/runs/43699306774) |
| `20f9b9dd2e0c1c9462cfa128775becc5df169cba` | feat(anilist): map imported entries safely (#22) | green | [43699323626](https://github.com/SakibShahariar/aniyori/actions/runs/43699323626) |
| `e569e6ef083b4cc264834caf344c7b4a94316b95` | refactor(anilist): centralize library import mapping (#22) | green | [43699330668](https://github.com/SakibShahariar/aniyori/actions/runs/43699330668) |
| `d0fa66e6ef80fd451c33fca2f020155f3f00a3ba` | test(anilist): cover remote library import mapping (#22) | green | [43699339194](https://github.com/SakibShahariar/aniyori/actions/runs/43699339194) |
| `57d93b14fda15404b2e496a7383f8e963370070f` | feat(anilist): detect sync conflicts without overwrites (#22) | green | [43699366709](https://github.com/SakibShahariar/aniyori/actions/runs/43699366709) |
| `6aa647ac3fe78c9722cc1e7dbb77fb78ede665fc` | test(anilist): cover conservative sync conflict planning (#22) | green | [43699377034](https://github.com/SakibShahariar/aniyori/actions/runs/43699377034) |
| `d34c7c162649203c2a14dcc56b3136b41d3ddec5` | feat(anilist): add conflict-reviewed two-way sync (#22) | green | [43699409719](https://github.com/SakibShahariar/aniyori/actions/runs/43699409719) |
| `9cd7a3107fade477dca3e979c3c98a224f7bde43` | fix(anilist): validate sync targets and preserve local IDs (#22) | green | [43699454474](https://github.com/SakibShahariar/aniyori/actions/runs/43699454474) |
| `ff2af202073408fad6bb1d73af5f6dab806320ee` | refactor(anilist): use validated sync decisions (#22) | green | [43699462389](https://github.com/SakibShahariar/aniyori/actions/runs/43699462389) |
| `e070ff23d15c26e3f9c195f8e98da287c0be6439` | test(anilist): cover explicit sync resolution paths (#22) | green | [43699473272](https://github.com/SakibShahariar/aniyori/actions/runs/43699473272) |
| `b6ec1ed81c6812f69a9b6f4a287d4aaf10acdd5f` | fix(anilist): preview imported titles before sync (#22) | green | [43699480093](https://github.com/SakibShahariar/aniyori/actions/runs/43699480093) |
| `b8d67e5ff58a93625f44317c8f891e24005722cc` | fix(anilist): keep account controls responsive and consistent (#22) | green | [43699514091](https://github.com/SakibShahariar/aniyori/actions/runs/43699514091) |
| `83a87f98dae0aaf40f5c011e3c68c480cfee76eb` | fix(anilist): bound remote watch progress values (#22) | green | [43699535307](https://github.com/SakibShahariar/aniyori/actions/runs/43699535307) |
| `b299eab0f786a1a71343c8c10ce52dac952240dc` | fix(anilist): validate imported media identity (#22) | green | [43699539348](https://github.com/SakibShahariar/aniyori/actions/runs/43699539348) |
| `4724969e77723a745220bef539df0a981b9f188e` | test(anilist): cover malformed account and media identity data (#22) | green | [43699555195](https://github.com/SakibShahariar/aniyori/actions/runs/43699555195) |
| `b310b6d428d264f7e1c132ad8ff0bf425e1e549e` | fix(anilist): reject control characters in bearer tokens (#22) | green | [43699592133](https://github.com/SakibShahariar/aniyori/actions/runs/43699592133) |
| `c9c4651dd803c33b778e1962d5f52dac952240dc` | fix(anilist): bound sync progress to local limits (#22) | green | [43699595394](https://github.com/SakibShahariar/aniyori/actions/runs/43699595394) |
| `d2c7064940b80a24442e4cca183b934477976eea` | test(anilist): cover token and progress bounds (#22) | green | [43699609759](https://github.com/SakibShahariar/aniyori/actions/runs/43699609759) |

No regression or red run was observed in this range.

- Reviewed checkpoint: `d2c7064940b80a24442e4cca183b934477976eea`

## Reviewed range: 2026-11-15 — AniList follow-up validation (#22)

Reviewed the commits after checkpoint `d2c7064940b80a24442e4cca183b934477976eea` through `69502c905cb556af057d3b6764e8d76b3654ebcf`.

| Commit SHA | Subject | CI result | Workflow run |
|---|---|---|---|
| `3020b5cc1f5ce50b5cf38e7ed185b971cab2d5af` | docs(anilist): document account setup and sync (#22) | green | [43699723510](https://github.com/SakibShahariar/aniyori/actions/runs/43699723510) |
| `2511c09f1670c161f7a542aba776d4eec21f7918` | fix(anilist): disable connection without a secure keyring (#22) | green | [43699758044](https://github.com/SakibShahariar/aniyori/actions/runs/43699758044) |
| `a526e5df8f994360ccee7cbddc9d9f47d78e1ac2` | fix(anilist): clean up replaced account credentials safely (#22) | green | [43699795570](https://github.com/SakibShahariar/aniyori/actions/runs/43699795570) |
| `3725e8122a2361f189aae1b1b89d57275c915eae` | fix(anilist): disclose broad AniList OAuth permissions (#22) | green | [43699806903](https://github.com/SakibShahariar/aniyori/actions/runs/43699806903) |
| `43340924f281ad3250e8da0a8eae39b5df8f4902` | fix(anilist): deduplicate entries across custom lists (#22) | red — test expectation was updated in the following commit | [43699849647](https://github.com/SakibShahariar/aniyori/actions/runs/43699849647) |
| `69502c905cb556af057d3b6764e8d76b3654ebcf` | test(anilist): cover custom-list duplicate handling (#22) | green — corrected the obsolete duplicate-rejection expectation; current head passes | [43699853998](https://github.com/SakibShahariar/aniyori/actions/runs/43699853998) |

The single red run above was caused by the existing test still expecting duplicate custom-list entries to be rejected after the implementation changed to deduplicate them. The follow-up commit updated the test to cover identical duplicates and conflicting duplicates; its full Tests workflow passed. No history was rewritten.

- Reviewed checkpoint: `69502c905cb556af057d3b6764e8d76b3654ebcf`

## Reviewed range: 2026-11-15 — documentation follow-up (#22)

| Commit SHA | Subject | CI result | Workflow run |
|---|---|---|---|
| `1c2f1aef9c962f95e22d134fa1aaa70096d045d0` | docs(anilist): clarify keyring and custom-list behavior (#22) | green | [43699922263](https://github.com/SakibShahariar/aniyori/actions/runs/43699922263) |

- Reviewed checkpoint: `1c2f1aef9c962f95e22d134fa1aaa70096d045d0`

## Reviewed range: 2026-11-15 — project OAuth Client ID supplied (#22)

The owner supplied public AniList Client ID `57061`. It is bundled as the default in the account OAuth helper and prefilled in the dialog. No client secret was added.

| Commit SHA | Subject | CI result | Workflow run |
|---|---|---|---|
| `39cdde603d78ec51d1e7b5a66e8c159d0c97efff` | feat(anilist): bundle project OAuth client ID (#22) | green | [43700901419](https://github.com/SakibShahariar/aniyori/actions/runs/43700901419) |
| `cad48baa6c9071daf3f70adf4935ccf9b6f5ace3` | feat(anilist): prefill project OAuth client ID (#22) | green | [43700904905](https://github.com/SakibShahariar/aniyori/actions/runs/43700904905) |
| `86327b9b640d7aadf1852ca16d565e5884a21849` | docs(anilist): publish project OAuth client setup (#22) | green | [43700907370](https://github.com/SakibShahariar/aniyori/actions/runs/43700907370) |
| `9f425957bfe6904b2285198a52cd908da9d01313` | test(anilist): verify bundled project client ID (#22) | green | [43700938304](https://github.com/SakibShahariar/aniyori/actions/runs/43700938304) |
| `c83e701b40cd87cb13a1dcfb12dcea8bc9443fc8` | docs(anilist): confirm bundled public client ID (#22) | green | [43700954754](https://github.com/SakibShahariar/aniyori/actions/runs/43700954754) |

No red CI runs were observed in this range. The automated test confirms the bundled ID is used in the implicit-grant authorization URL.

- Reviewed checkpoint: `c83e701b40cd87cb13a1dcfb12dcea8bc9443fc8`


## Reviewed range: 2026-11-06 through 2026-11-15 — incremental audit

Reviewed every commit after the previous checkpoint `13a833c803d560f37db7b1808f1667307b34b77c` through `fc229cb597838645b567eb072023b7b956395029`. The comparison returned 69 commits. Every commit had a corresponding completed push-triggered Tests workflow: **64 green, 5 red**. The red results are preserved below and were followed by green corrections; no history was rewritten.

| Commit SHA | Subject | Date | CI result | Tests run |
|---|---|---|---|---|
| `26fb8102d798a63ccebef0f09c2acf2fb6fb452f` | docs(maintenance): record preset and scanner CI availability | 2026-11-06 | green | [42281153274](https://github.com/SakibShahariar/aniyori/actions/runs/42281153274) |
| `4f3f15d386786ccd1bc2f1e860e295afebe6a237` | docs: move privacy details into dedicated guide | 2026-11-08 | green | [42512004203](https://github.com/SakibShahariar/aniyori/actions/runs/42512004203) |
| `f4542c9ec233be37440651ece80c2fcdb132db3c` | docs: modernize and streamline Aniyori README | 2026-11-08 | green | [42512018068](https://github.com/SakibShahariar/aniyori/actions/runs/42512018068) |
| `5579b08e3747f0817c6ab9f7c1d8ec88df2a41fb` | fix(gui): use adaptive libadwaita main layout (#90) | 2026-11-11 | green | [42932046781](https://github.com/SakibShahariar/aniyori/actions/runs/42932046781) |
| `03bfa52f4108224b8b555a6bc216a8cccf9b0bdc` | fix(gui): wrap bulk actions for narrow windows (#90) | 2026-11-11 | green | [42932092383](https://github.com/SakibShahariar/aniyori/actions/runs/42932092383) |
| `85a28a731aee746eedfddd7baeed8379fd6dae2c` | refactor(gui): use preferences dialog for playback settings (#90) | 2026-11-11 | green | [42932153487](https://github.com/SakibShahariar/aniyori/actions/runs/42932153487) |
| `b9d3af54239158e6a338c746f5fcc14b44f3e905` | refactor(gui): use preferences rows for notifications (#90) | 2026-11-11 | green | [42932247719](https://github.com/SakibShahariar/aniyori/actions/runs/42932247719) |
| `051535176a0097c2710874875586123bd9c1ef72` | refactor(gui): use preference rows for network settings (#90) | 2026-11-11 | green | [42932304372](https://github.com/SakibShahariar/aniyori/actions/runs/42932304372) |
| `32da4df8a445038359a622cf9c91d296c46d072b` | docs(qa): add main window and preferences checks (#90) | 2026-11-11 | green | [42932339791](https://github.com/SakibShahariar/aniyori/actions/runs/42932339791) |
| `0baadd357f848d14b2223d14d7f7ece5fc1a90c7` | fix(gui): reduce default library row width (#90) | 2026-11-11 | red | [42932528362](https://github.com/SakibShahariar/aniyori/actions/runs/42932528362) |
| `85bad889ce8c09ee03a704992ea627d245951436` | test(gui): cover compact default library columns (#90) | 2026-11-11 | red | [42932537122](https://github.com/SakibShahariar/aniyori/actions/runs/42932537122) |
| `b7904160ae5c72875b669c634792958b8b817930` | fix(gui): adapt library rows at narrow widths (#90) | 2026-11-11 | red | [42932575648](https://github.com/SakibShahariar/aniyori/actions/runs/42932575648) |
| `8bfbf58b97c5f003a18fa66adae853d82fc5cb17` | docs(qa): cover compact library row behavior (#90) | 2026-11-11 | red | [42932599620](https://github.com/SakibShahariar/aniyori/actions/runs/42932599620) |
| `5f35894bc80189245266c4c4537d9c372f0b692e` | test(gui): update reset test for compact defaults (#90) | 2026-11-11 | green | [42932632240](https://github.com/SakibShahariar/aniyori/actions/runs/42932632240) |
| `91c5e1b05b377e9557c06120c6ca39a642286b7f` | fix(gui): split release controls for narrow windows (#90) | 2026-11-11 | green | [42932748215](https://github.com/SakibShahariar/aniyori/actions/runs/42932748215) |
| `3e81bbd629a954f088b5643c592e8ed82f19fc54` | docs(qa): cover compact release controls (#90) | 2026-11-11 | green | [42932758122](https://github.com/SakibShahariar/aniyori/actions/runs/42932758122) |
| `7993bafdd144ab472e28388358e66ada73bc727d` | refactor(gui): make download queue an adaptive dialog (#90) | 2026-11-11 | green | [42932819040](https://github.com/SakibShahariar/aniyori/actions/runs/42932819040) |
| `ba0bcd44c0edeb22c381c94273d96a4c33ea2d54` | docs(qa): cover adaptive download queue dialog (#90) | 2026-11-11 | green | [42932829136](https://github.com/SakibShahariar/aniyori/actions/runs/42932829136) |
| `d8efee4b2a1ec2e054919e259c398588c3d7c40e` | fix(gui): let library grid use one column when narrow (#90) | 2026-11-11 | green | [42932854330](https://github.com/SakibShahariar/aniyori/actions/runs/42932854330) |
| `8c72a70a01745265975abedff42a7ad98d2c42fd` | docs(qa): cover narrow grid card sizing (#90) | 2026-11-11 | green | [42932861039](https://github.com/SakibShahariar/aniyori/actions/runs/42932861039) |
| `e7fd0f0b3c18a20f4d452d0aeee62c014b953503` | refactor(gui): use adaptive dialogs for library tools (#90) | 2026-11-11 | green | [42932923024](https://github.com/SakibShahariar/aniyori/actions/runs/42932923024) |
| `36a16271ba83f98d345cf5213358730226a331a1` | refactor(gui): use adaptive dialogs for history and sharing (#90) | 2026-11-11 | green | [42932951744](https://github.com/SakibShahariar/aniyori/actions/runs/42932951744) |
| `2129aaf659f5ecf392342ab7f3099647a2888c5b` | docs(qa): cover adaptive library dialogs (#90) | 2026-11-11 | green | [42932963445](https://github.com/SakibShahariar/aniyori/actions/runs/42932963445) |
| `ab4c3207c194297f8aea21faf8669ab2349a5d44` | fix(gui): add native headers to adaptive dialogs (#90) | 2026-11-11 | green | [42933022317](https://github.com/SakibShahariar/aniyori/actions/runs/42933022317) |
| `a87ef1f269cdb39b3cc9d69566139d40abca90bb` | feat(anilist): add desktop OAuth account helpers (#22) | 2026-11-15 | green | [43699199565](https://github.com/SakibShahariar/aniyori/actions/runs/43699199565) |
| `970b42a8f4df52116e3d54fdf03d17c2b8ee6197` | test(anilist): cover desktop OAuth helpers (#22) | 2026-11-15 | green | [43699212965](https://github.com/SakibShahariar/aniyori/actions/runs/43699212965) |
| `5d254d033222f7652e7e04f87141ad98a033b34b` | feat(anilist): add authenticated library API support (#22) | 2026-11-15 | green | [43699231326](https://github.com/SakibShahariar/aniyori/actions/runs/43699231326) |
| `81ef8eb8150fabd97dd69168cba695bb2d5a3437` | test(anilist): cover authenticated library operations (#22) | 2026-11-15 | green | [43699251785](https://github.com/SakibShahariar/aniyori/actions/runs/43699251785) |
| `bd3730f5346fa2319112099ef763924567112ea2` | fix(anilist): reject malformed list status values (#22) | 2026-11-15 | green | [43699258790](https://github.com/SakibShahariar/aniyori/actions/runs/43699258790) |
| `6da2cc9a3a08595a758db40cdf693ac03ba3660f` | feat(anilist): add account connection and import dialog (#22) | 2026-11-15 | green | [43699293660](https://github.com/SakibShahariar/aniyori/actions/runs/43699293660) |
| `361f6c1861a4d45c6a6c6c3f2042690c02863139` | feat(anilist): expose account integration in app menu (#22) | 2026-11-15 | green | [43699306774](https://github.com/SakibShahariar/aniyori/actions/runs/43699306774) |
| `20f9b9dd2e0c1c9462cfa128775becc5df169cba` | feat(anilist): map imported entries safely (#22) | 2026-11-15 | green | [43699323626](https://github.com/SakibShahariar/aniyori/actions/runs/43699323626) |
| `e569e6ef083b4cc264834caf344c7b4a94316b95` | refactor(anilist): centralize library import mapping (#22) | 2026-11-15 | green | [43699330668](https://github.com/SakibShahariar/aniyori/actions/runs/43699330668) |
| `d0fa66e6ef80fd451c33fca2f020155f3f00a3ba` | test(anilist): cover remote library import mapping (#22) | 2026-11-15 | green | [43699339194](https://github.com/SakibShahariar/aniyori/actions/runs/43699339194) |
| `57d93b14fda15404b2e496a7383f8e963370070f` | feat(anilist): detect sync conflicts without overwrites (#22) | 2026-11-15 | green | [43699366709](https://github.com/SakibShahariar/aniyori/actions/runs/43699366709) |
| `6aa647ac3fe78c9722cc1e7dbb77fb78ede665fc` | test(anilist): cover conservative sync conflict planning (#22) | 2026-11-15 | green | [43699377034](https://github.com/SakibShahariar/aniyori/actions/runs/43699377034) |
| `d34c7c162649203c2a14dcc56b3136b41d3ddec5` | feat(anilist): add conflict-reviewed two-way sync (#22) | 2026-11-15 | green | [43699409719](https://github.com/SakibShahariar/aniyori/actions/runs/43699409719) |
| `9cd7a3107fade477dca3e979c3c98a224f7bde43` | fix(anilist): validate sync targets and preserve local IDs (#22) | 2026-11-15 | green | [43699454474](https://github.com/SakibShahariar/aniyori/actions/runs/43699454474) |
| `ff2af202073408fad6bb1d73af5f6dab806320ee` | refactor(anilist): use validated sync decisions (#22) | 2026-11-15 | green | [43699462389](https://github.com/SakibShahariar/aniyori/actions/runs/43699462389) |
| `e070ff23d15c26e3f9c195f8e98da287c0be6439` | test(anilist): cover explicit sync resolution paths (#22) | 2026-11-15 | green | [43699473272](https://github.com/SakibShahariar/aniyori/actions/runs/43699473272) |
| `b6ec1ed81c6812f69a9b6f4a287d4aaf10acdd5f` | fix(anilist): preview imported titles before sync (#22) | 2026-11-15 | green | [43699480093](https://github.com/SakibShahariar/aniyori/actions/runs/43699480093) |
| `b8d67e5ff58a93625f44317c8f891e24005722cc` | fix(anilist): keep account controls responsive and consistent (#22) | 2026-11-15 | green | [43699514091](https://github.com/SakibShahariar/aniyori/actions/runs/43699514091) |
| `83a87f98dae0aaf40f5c011e3c68c480cfee76eb` | fix(anilist): bound remote watch progress values (#22) | 2026-11-15 | green | [43699535307](https://github.com/SakibShahariar/aniyori/actions/runs/43699535307) |
| `b299eab0f786a1a71343c8c10ce52bcac65ac7d7` | fix(anilist): validate imported media identity (#22) | 2026-11-15 | green | [43699539348](https://github.com/SakibShahariar/aniyori/actions/runs/43699539348) |
| `4724969e77723a745220bef539df0a981b9f188e` | test(anilist): cover malformed account and media identity data (#22) | 2026-11-15 | green | [43699555195](https://github.com/SakibShahariar/aniyori/actions/runs/43699555195) |
| `b310b6d428d264f7e1c132ad8ff0bf425e1e549e` | fix(anilist): reject control characters in bearer tokens (#22) | 2026-11-15 | green | [43699592133](https://github.com/SakibShahariar/aniyori/actions/runs/43699592133) |
| `c9c4651dd803c33b778e1962d5f52dac952240dc` | fix(anilist): bound sync progress to local limits (#22) | 2026-11-15 | green | [43699595394](https://github.com/SakibShahariar/aniyori/actions/runs/43699595394) |
| `d2c7064940b80a24442e4cca183b934477976eea` | test(anilist): cover token and progress bounds (#22) | 2026-11-15 | green | [43699609759](https://github.com/SakibShahariar/aniyori/actions/runs/43699609759) |
| `3020b5cc1f5ce50b5cf38e7ed185b971cab2d5af` | docs(anilist): document account setup and sync (#22) | 2026-11-15 | green | [43699723510](https://github.com/SakibShahariar/aniyori/actions/runs/43699723510) |
| `2511c09f1670c161f7a542aba776d4eec21f7918` | fix(anilist): disable connection without a secure keyring (#22) | 2026-11-15 | green | [43699758044](https://github.com/SakibShahariar/aniyori/actions/runs/43699758044) |
| `a526e5df8f994360ccee7cbddc9d9f47d78e1ac2` | fix(anilist): clean up replaced account credentials safely (#22) | 2026-11-15 | green | [43699795570](https://github.com/SakibShahariar/aniyori/actions/runs/43699795570) |
| `3725e8122a2361f189aae1b1b89d57275c915eae` | fix(anilist): disclose broad AniList OAuth permissions (#22) | 2026-11-15 | green | [43699806903](https://github.com/SakibShahariar/aniyori/actions/runs/43699806903) |
| `43340924f281ad3250e8da0a8eae39b5df8f4902` | fix(anilist): deduplicate entries across custom lists (#22) | 2026-11-15 | red | [43699849647](https://github.com/SakibShahariar/aniyori/actions/runs/43699849647) |
| `69502c905cb556af057d3b6764e8d76b3654ebcf` | test(anilist): cover custom-list duplicate handling (#22) | 2026-11-15 | green | [43699853998](https://github.com/SakibShahariar/aniyori/actions/runs/43699853998) |
| `1c2f1aef9c962f95e22d134fa1aaa70096d045d0` | docs(anilist): clarify keyring and custom-list behavior (#22) | 2026-11-15 | green | [43699922263](https://github.com/SakibShahariar/aniyori/actions/runs/43699922263) |
| `74d654742f3a08aebee554cf9b2181cdf869b2ab` | docs(anilist): document sync data boundaries (#22) | 2026-11-15 | green | [43699989080](https://github.com/SakibShahariar/aniyori/actions/runs/43699989080) |
| `39cdde603d78ec51d1e7b5a66e8c159d0c97efff` | feat(anilist): bundle project OAuth client ID (#22) | 2026-11-15 | green | [43700901419](https://github.com/SakibShahariar/aniyori/actions/runs/43700901419) |
| `cad48baa6c9071daf3f70adf4935ccf9b6f5ace3` | feat(anilist): prefill project OAuth client ID (#22) | 2026-11-15 | green | [43700904905](https://github.com/SakibShahariar/aniyori/actions/runs/43700904905) |
| `86327b9b640d7aadf1852ca16d565e5884a21849` | docs(anilist): publish project OAuth client setup (#22) | 2026-11-15 | green | [43700907370](https://github.com/SakibShahariar/aniyori/actions/runs/43700907370) |
| `9f425957bfe6904b2285198a52cd908da9d01313` | test(anilist): verify bundled project client ID (#22) | 2026-11-15 | green | [43700938304](https://github.com/SakibShahariar/aniyori/actions/runs/43700938304) |
| `c83e701b40cd87cb13a1dcfb12dcea8bc9443fc8` | docs(anilist): confirm bundled public client ID (#22) | 2026-11-15 | green | [43700954754](https://github.com/SakibShahariar/aniyori/actions/runs/43700954754) |
| `7af403c6fda5d3d683bfd8b90b6d784f827d5524` | docs(anilist): record project OAuth client CI results (#22) | 2026-11-15 | green | [43701016561](https://github.com/SakibShahariar/aniyori/actions/runs/43701016561) |
| `cb4a91eb6e6a92b041bdc807124d2365995aea06` | fix(ui): align AniList dialogs with libadwaita (#90) | 2026-11-15 | green | [43702157486](https://github.com/SakibShahariar/aniyori/actions/runs/43702157486) |
| `1d1cbf965922df44dd1b180319ef48fc3be9fc6c` | fix(ui): use adaptive dialog for season discovery (#90) | 2026-11-15 | green | [43702804916](https://github.com/SakibShahariar/aniyori/actions/runs/43702804916) |
| `9448c6677fb3afbcea93cc34f8926458a7f57ad2` | fix(ui): move library search into page toolbar (#90) | 2026-11-15 | green | [43704328617](https://github.com/SakibShahariar/aniyori/actions/runs/43704328617) |
| `32241e8919c7991bc3e01cd129bfca3bf2dd847d` | fix(ui): wrap library controls at narrow widths (#90) | 2026-11-15 | green | [43704453366](https://github.com/SakibShahariar/aniyori/actions/runs/43704453366) |
| `7e26183046d446b91f5c36503a6a77b42b93ff6e` | fix(ui): group adaptive library actions (#90) | 2026-11-15 | green | [43704481832](https://github.com/SakibShahariar/aniyori/actions/runs/43704481832) |
| `98426a9aca746647c4e5dedc3d59816cca6442ed` | fix(ui): compact library row and card actions (#90) | 2026-11-15 | green | [43705072008](https://github.com/SakibShahariar/aniyori/actions/runs/43705072008) |
| `fc229cb597838645b567eb072023b7b956395029` | docs(anilist): update project integration status (#22) | 2026-11-15 | green | [43705187828](https://github.com/SakibShahariar/aniyori/actions/runs/43705187828) |

### Red-run investigation: compact library defaults (#90)

Four commits failed because `tests/test_library_layout.py::test_reset_restores_view_defaults_without_changing_other_view` still attempted to remove `source` from the default visible list after the default layout had intentionally hidden that column. The error was `ValueError: list.remove(x): x not in list`; this was a stale test assumption, not a production-code failure.

- `0baadd357f848d14b2223d14d7f7ece5fc1a90c7` — [run 42932528362](https://github.com/SakibShahariar/aniyori/actions/runs/42932528362), failed at test line 43.
- `85bad889ce8c09ee03a704992ea627d245951436` — [run 42932537122](https://github.com/SakibShahariar/aniyori/actions/runs/42932537122), failed at test line 51.
- `b7904160ae5c72875b669c634792958b8b817930` — [run 42932575648](https://github.com/SakibShahariar/aniyori/actions/runs/42932575648), same stale assumption at test line 51.
- `8bfbf58b97c5f003a18fa66adae853d82fc5cb17` — [run 42932599620](https://github.com/SakibShahariar/aniyori/actions/runs/42932599620), same stale assumption at test line 51.
- Correction: `5f35894bc80189245266c4c4537d9c372f0b692e` updates the reset test to use the current default columns; [run 42932632240](https://github.com/SakibShahariar/aniyori/actions/runs/42932632240) passed.

### Red-run investigation: AniList custom-list deduplication (#22)

- `43340924f281ad3250e8da0a8eae39b5df8f4902` — [run 43699849647](https://github.com/SakibShahariar/aniyori/actions/runs/43699849647) failed because an existing test still expected duplicate custom-list entries to raise `AniListError`, while the new import behavior intentionally deduplicates identical entries.
- Correction: `69502c905cb556af057d3b6764e8d76b3654ebcf` updates the expectation and covers conflicting duplicates; [run 43699853998](https://github.com/SakibShahariar/aniyori/actions/runs/43699853998) passed.

### Checkpoint

- Reviewed range: `13a833c803d560f37db7b1808f1667307b34b77c` → `fc229cb597838645b567eb072023b7b956395029`
- Result: 69 commits reviewed; 64 green, 5 red with green follow-up corrections.
- New checkpoint: `fc229cb597838645b567eb072023b7b956395029`


## Reviewed range: 2026-11-15 — Home dashboard (#91)

The range after the previous checkpoint `fc229cb597838645b567eb072023b7b956395029` was reviewed commit by commit. The earlier accessibility commit `ea1681a` has a directly verified green Actions run. For the dashboard commits below, the combined commit-status endpoint returned an empty status list; this is recorded as **unavailable**, not green. The available workflow-run lookup only exposes pull-request-triggered runs, so it did not provide push-run evidence. The repository's `.github/workflows/tests.yml` confirms that pushes to `main` trigger compileall and the full unittest suite, but no run IDs/results could be retrieved in this audit.

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `ea1681a1e10c633d7d92bd46ff251b7ecef0147b` | fix(a11y): label library actions for assistive tech (#90) | green | [43705434990](https://github.com/SakibShahariar/aniyori/actions/runs/43705434990) |
| `f0547dfdbcded0096740ff7db91bda8586202599` | feat(ui): add a data-backed home dashboard (#91) | unavailable | Combined status lookup returned no entries |
| `257ee120ff7bba23beae119548fa62ad401a51bf` | fix(ui): keep dashboard labels GTK-compatible (#91) | unavailable | Combined status lookup returned no entries |
| `602af12ca386856b62fa71297f35d4ef2e796d21` | fix(ui): keep home dashboard scrollable and current (#91) | unavailable | Combined status lookup returned no entries |
| `7ff3d15846295f753ee61b1ca6ba1a352826702a` | fix(ui): wrap dashboard actions and status tiles (#91) | unavailable | Combined status lookup returned no entries |
| `abcaffc2916d3abf0726ac763e349deb6148db32` | fix(ui): refresh dashboard after library changes (#91) | unavailable | Combined status lookup returned no entries |
| `66936eddb8abf27e6b8dc07c52648c3e3b52a099` | feat(ui): add tested dashboard data selectors (#91) | unavailable | Combined status lookup returned no entries |
| `5aedea761e80c8e125e3ca7fadaf3eadd51f464e` | test(ui): cover dashboard data selection (#91) | unavailable | Combined status lookup returned no entries |
| `1ffd8ee05f6778668e6c14df3b0365098b023709` | refactor(ui): use tested dashboard data selectors (#91) | unavailable | Combined status lookup returned no entries |
| `9034867ddc70c8fcdb1ef75476b9d3d56f78f609` | feat(ui): add poster-led dashboard cards (#91) | unavailable | Combined status lookup returned no entries |
| `e676b23fa39a808c5da9b9c2c40720a3238a2898` | fix(ui): keep dashboard cards GTK 4.8 compatible (#91) | unavailable | Combined status lookup returned no entries |
| `123324c47f08e94567d5db0fcfbb0f8113c3d8de` | feat(ui): complete dashboard hero and quick actions (#91) | unavailable | Combined status lookup returned no entries |
| `f01963f69e643cd23d940af975c49fb236ec1837` | docs(qa): add home dashboard verification checklist (#91) | unavailable | Combined status lookup returned no entries |
| `3493737a81616e90a7969c8597d5a4d8d45a4589` | style(ui): simplify dashboard hero spacing (#91) | unavailable | Combined status lookup returned no entries |
| `f6735e12e9e2d94d6ea116d80be64a80c35b452f` | feat(ui): add adaptive libadwaita navigation sidebar (#91) | unavailable | Combined status lookup returned no entries |
| `5064a840266b76508694c4170d1e5b2437cc52f0` | refactor(ui): share adaptive navigation breakpoint (#91) | unavailable | Combined status lookup returned no entries |

- Workflow definition inspected: `.github/workflows/tests.yml`; push to `main` runs Python 3.12 compileall and `python -m unittest discover -s tests -v`.
- No result is inferred from an empty status response. The dashboard range remains CI-unverified and must be revisited when push-run evidence is accessible.
- Live GTK desktop validation remains outstanding; the QA checklist now includes Home dashboard and navigation checks.

### Updated checkpoint

- Previous checkpoint: `fc229cb597838645b567eb072023b7b956395029`
- Reviewed through: `5064a840266b76508694c4170d1e5b2437cc52f0`
- New checkpoint: `5064a840266b76508694c4170d1e5b2437cc52f0`


### Follow-up commits after the dashboard checkpoint

The following commits were checked individually. The combined commit-status endpoint returned no status records for each; all are **unavailable**, not green. The push workflow definition remains configured to run compileall and the full unittest suite on `main`, but run evidence could not be retrieved.

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `58d0f7a22ad773b65cb219b44abf7957c05b4fcb` | docs(maintenance): audit dashboard commit CI evidence (#91) | unavailable | Combined status lookup returned no entries |
| `35066136dbc27e98aa40510717df2d960268ddff` | docs(qa): verify adaptive dashboard navigation (#91) | unavailable | Combined status lookup returned no entries |
| `fac97a48ba4f8a17ba755bffe2ab4b9147bea1d0` | fix(ui): keep collapsed navigation actions reliable (#91) | unavailable | Combined status lookup returned no entries |
| `ecc5da1c982315a51ded070f052a0f0d4d738370` | docs(qa): cover repeated collapsed navigation selection (#91) | unavailable | Combined status lookup returned no entries |

- Previous checkpoint: `5064a840266b76508694c4170d1e5b2437cc52f0`
- Reviewed through: `ecc5da1c982315a51ded070f052a0f0d4d738370`
- New checkpoint: `ecc5da1c982315a51ded070f052a0f0d4d738370`
- Outstanding: retrieve actual push-triggered Actions results for the unavailable commits and rerun any failures before marking CI green.


### Startup behavior follow-up

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `5207c9e3fd558665c1e2cbc7deb1a7b246d420d4` | fix(ui): open home content in collapsed navigation (#91) | unavailable | Combined status lookup returned no entries |

- Previous checkpoint: `ecc5da1c982315a51ded070f052a0f0d4d738370`
- Reviewed through: `5207c9e3fd558665c1e2cbc7deb1a7b246d420d4`
- New checkpoint: `5207c9e3fd558665c1e2cbc7deb1a7b246d420d4`
- The missing push-run result remains unresolved; do not interpret unavailable as a pass.


### Recently Added data follow-up

The following commits were checked individually. Every combined status lookup returned an empty status list, so each result is **unavailable**, not green. Push-run evidence remains inaccessible through the available Actions lookup.

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `0f884b092373f0379fd562aa19b1052d4586af3f` | feat(storage): expose library creation timestamps (#91) | unavailable | Combined status lookup returned no entries |
| `1c89db089a568bbbdd1f505b7fee4636bf5b77e3` | feat(ui): select recently added dashboard entries (#91) | unavailable | Combined status lookup returned no entries |
| `e691785bceae8ca955658e90187f601a67174238` | test(ui): verify recently added dashboard ordering (#91) | unavailable | Combined status lookup returned no entries |
| `feb25937da4513766e427053b3e2928092776163` | fix(ui): order recently added by creation date (#91) | unavailable | Combined status lookup returned no entries |
| `505dc47e3dd8187ba7e52469004a7c55cd3391a5` | test(storage): cover library creation timestamps (#91) | unavailable | Combined status lookup returned no entries |
| `fe89f8c3792890e08d0d7e63e5756340bf505e06` | refactor(ui): keep dashboard selectors focused (#91) | unavailable | Combined status lookup returned no entries |
| `7b547bf25531d38258486d48f6d9c70d59f9b28b` | test(ui): focus dashboard tests on creation ordering (#91) | unavailable | Combined status lookup returned no entries |
| `1d6c516a27c564ba45503795da8365b1a523fd0d` | docs(qa): align dashboard checks with added-date cards (#91) | unavailable | Combined status lookup returned no entries |
| `9004593e4b3a6b754ec8c95ce8497d31720b4a88` | test(storage): preserve creation timestamps across edits (#91) | unavailable | Combined status lookup returned no entries |

- Previous checkpoint: `5207c9e3fd558665c1e2cbc7deb1a7b246d420d4`
- Reviewed through: `9004593e4b3a6b754ec8c95ce8497d31720b4a88`
- New checkpoint: `9004593e4b3a6b754ec8c95ce8497d31720b4a88`
- The Home page now labels the section Recently Added and orders it using the database's immutable `created_at` field, not `updated_at`.


### Dashboard ordering and totals follow-up

Each commit below was checked through the combined status endpoint. All returned empty status lists and are recorded as **unavailable**, not green. No push-triggered run result was exposed.

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `5b02392466c23a3035b655a66b147d419fb3f814` | feat(ui): prioritize recently watched dashboard entries (#91) | unavailable | Combined status lookup returned no entries |
| `8469ae959a98eae1e8d89a4083c07b2028b5c25f` | test(ui): verify continue watching recency order (#91) | unavailable | Combined status lookup returned no entries |
| `af38cc6e7db594c9025559eb0b4389aab714dcdf` | fix(ui): order continue watching by recent activity (#91) | unavailable | Combined status lookup returned no entries |
| `1854444ad9efe8316cd788c04ca7d4f2bcdf55a5` | feat(ui): show total library count on dashboard (#91) | unavailable | Combined status lookup returned no entries |
| `695fb5dc6e499c7a1f06d99352a41f8b5753020e` | docs(qa): verify dashboard ordering and totals (#91) | unavailable | Combined status lookup returned no entries |

- Previous checkpoint: `9004593e4b3a6b754ec8c95ce8497d31720b4a88`
- Reviewed through: `695fb5dc6e499c7a1f06d99352a41f8b5753020e`
- New checkpoint: `695fb5dc6e499c7a1f06d99352a41f8b5753020e`
- Outstanding: obtain actual push-triggered Actions results and execute the desktop checklist before treating the redesign as validated.


### Anime Details follow-up

Each commit was checked individually. The combined status endpoint returned no status records, and the commit workflow-run lookup returned no runs. These results are **unavailable**, not green; the workflow-run wrapper is documented to return only pull-request-triggered runs.

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `5b100565b49a025e523c38a4fd8be72ef5985c38` | feat(ui): add native anime details dialog (#91) | unavailable | Status list empty; PR-only run lookup empty |
| `45d221acd00f38298117366ff0af34edfd26962d` | fix(ui): make anime details content scrollable (#91) | unavailable | Status list empty; PR-only run lookup empty |
| `c370ff2ebb045839c0a073f8f79613e16c95fb33` | docs(qa): cover anime details dialog interactions (#91) | unavailable | Status list empty; PR-only run lookup empty |

- Previous checkpoint: `a4bd735096d1d8566486483646df772bd76fc9eb`
- Reviewed through: `c370ff2ebb045839c0a073f8f79613e16c95fb33`
- New checkpoint: `c370ff2ebb045839c0a073f8f79613e16c95fb33`
- Outstanding: retrieve push-triggered Actions runs and execute the Home/Details live-desktop checklist before marking the redesign validated.


## Reviewed range: 2026-11-15 — library and preset follow-ups

Reviewed every commit after the prior ledger checkpoint `c370ff2ebb045839c0a073f8f79613e16c95fb33` through the current `main` tip. Combined-status queries were run individually for all 18 commits below; every query returned an empty status list. No run result is inferred from that absence. The repository's push workflow is configured to run compileall and the full unittest suite, but this audit did not expose the push-run IDs/results. All entries are **unavailable**, not green.

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `2a903a2fbd346c7122ae041fa55d0f7c68b6b67e` | fix(ui): align My List grid cards with Home (#91) | unavailable | Combined status lookup empty |
| `95894cd127c259eb780286082847359147f88f3d` | docs(qa): cover My List grid card consistency (#91) | unavailable | Combined status lookup empty |
| `3a70cbfba268869d2f654a0141f4fe4f021594cf` | fix(a11y): label library artwork and progress (#84) | unavailable | Combined status lookup empty |
| `c98c85451ef500014e1e5b9d7dc9ef960c52a98f` | docs(qa): cover library artwork and progress labels (#84) | unavailable | Combined status lookup empty |
| `ef915fa9ee5bb9efeb2601c7aa4dd0ea6ae7f345` | fix(ui): wrap grid card actions for narrow widths (#91) | unavailable | Combined status lookup empty |
| `f3ceabfb2223c1b845c2bdc5701c3dc7a2ea2d16` | docs(qa): verify narrow grid card actions (#91) | unavailable | Combined status lookup empty |
| `d1b383dde02cdeee9f149e0e2d102514557ba271` | refactor(library): centralize widget cache signature (#15) | unavailable | Combined status lookup empty |
| `146588330ec330b6cf6930b1722a3f03f2930e66` | fix(library): preserve widget cache on selection (#15) | unavailable | Combined status lookup empty |
| `dcb987c0d62e82b93a42d6bffd2ea787d33f00a0` | test(library): cover widget cache signatures (#15) | unavailable | Combined status lookup empty |
| `62de6747866a7b69cee0c4cc1bd0543414b69e79` | docs(qa): cover library selection cache behavior (#15) | unavailable | Combined status lookup empty |
| `46b639c0c168f3230e4f14f20ebc4696cafd587c` | fix(library): preserve empty state across views (#90) | unavailable | Combined status lookup empty |
| `4ce9bb5157dd2e0d78e68473eeb00b08b6c0144e` | fix(ui): keep library empty state when switching views (#90) | unavailable | Combined status lookup empty |
| `4e9969f38a322f77427af58ffae1f569a74c6159` | test(ui): cover empty state across library views (#90) | unavailable | Combined status lookup empty |
| `7dee0157ff781f42f50e103eeb0a6ebc29bb90bd` | docs(qa): cover filtered empty state across views (#90) | unavailable | Combined status lookup empty |
| `e8eba78de6e8edee0f93c2141a1ca9576ba4fd75` | fix(library): retain selected view in saved presets (#89) | unavailable | Combined status lookup empty |
| `91c46c75578556279cc718d5cf0372a8cb0c280f` | fix(library): retain selected view in saved presets (#89) | unavailable | Combined status lookup empty |
| `74e535e15b93ad245e47ba8d09e948bd16350cc8` | test(library): cover preset view with empty results (#89) | unavailable | Combined status lookup empty |
| `3efe5d884ccc72cf77b8ea0f2d681665a7746079` | docs(qa): cover presets with filtered empty results (#89) | unavailable | Combined status lookup empty |

- Reviewed range: `c370ff2ebb045839c0a073f8f79613e16c95fb33` → `3efe5d884ccc72cf77b8ea0f2d681665a7746079`
- Result: 18 commits reviewed; 18 unavailable; no red or green result was exposed by the queried endpoint.
- New checkpoint: `3efe5d884ccc72cf77b8ea0f2d681665a7746079`
- Outstanding: retrieve the actual push-triggered Actions results and run the test suite before treating these changes as CI-verified. The live GTK checks for card sizing, selection, empty states, and presets remain outstanding.


### Preset-view helper cleanup and audit-ledger commit

These commits were checked individually through the combined-status endpoint. Each returned an empty status list, so each is **unavailable**, not green. The workflow-run wrapper returned no runs for the audit-ledger commit and is limited to pull-request-triggered runs.

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `b44b4889403619b45ea7fdb4158eb27d8d37ab36` | docs(maintenance): audit library follow-up CI evidence (#15) | unavailable | Combined status empty; workflow-run lookup empty |
| `7bbc129ab625915d7d079bdb46048ad666050b69` | refactor(library): simplify selected view helper (#89) | unavailable | Combined status empty |
| `615b01bdd024109b65fbbf03ff7b55e114cc5ed3` | refactor(library): simplify selected view capture (#89) | unavailable | Combined status empty |
| `a4436f449f240cadcb440f3346f4945d8efbfd5e` | test(library): simplify selected view regression (#89) | unavailable | Combined status empty |

- Previous checkpoint: `3efe5d884ccc72cf77b8ea0f2d681665a7746079`
- Reviewed through: `a4436f449f240cadcb440f3346f4945d8efbfd5e`
- New checkpoint: `a4436f449f240cadcb440f3346f4945d8efbfd5e`
- Outstanding: obtain push-triggered Actions results and run the complete unittest suite; the three helper-cleanup commits and prior 18-commit range remain CI-unverified.


### Post-audit ledger and render-path optimization

The commits below were checked individually. Combined-status queries returned empty lists; the available workflow-run lookup returned no run for the render optimization and is PR-triggered-only. Results are **unavailable**, not green.

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `2e055dfca5259728b5db30f5c24296ec17661543` | docs(maintenance): record preset helper CI evidence (#89) | unavailable | Combined status empty; workflow-run lookup empty |
| `f889e2fe5493c1bf2f3613e574180999a9285327` | perf(library): load edit timestamps only when sorting by recency (#15) | unavailable | Combined status empty; workflow-run lookup empty |

- Previous checkpoint: `a4436f449f240cadcb440f3346f4945d8efbfd5e`
- Reviewed through: `f889e2fe5493c1bf2f3613e574180999a9285327`
- New checkpoint: `f889e2fe5493c1bf2f3613e574180999a9285327`
- Outstanding: obtain push-triggered Actions results and run the complete test suite. Benchmark the library render path with a large library before estimating latency improvement.


### Library cache and episode-state follow-ups — 2026-11-15

The combined-status endpoint returned empty status lists for every commit below. To verify actual push-triggered CI, queried the repository Actions API by exact `head_sha` and inspected the associated completed workflow runs. Results:

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `d5bd9d6fb938216c0564cbd67adb63c572711a60` | docs(maintenance): record library render optimization CI (#15) | success | [43710941532](https://github.com/SakibShahariar/aniyori/actions/runs/43710941532) |
| `88c1526cbb3ccef822fc363b23e220fe78f5e5e8` | perf(library): reuse layout cache signature (#15) | failure | [43711236323](https://github.com/SakibShahariar/aniyori/actions/runs/43711236323) |
| `8d34de65fd514d32241746b9e2aca395fc1dce1e` | perf(library): compute layout signature once per render (#15) | failure | [43711241040](https://github.com/SakibShahariar/aniyori/actions/runs/43711241040) |
| `c891f712ddf2e2fdca130aff7cbd45c84dd738de` | test(library): cover shared layout cache signature (#15) | success | [43711244028](https://github.com/SakibShahariar/aniyori/actions/runs/43711244028) |
| `d8c68984862333e051c2acca73e3a12a6d13f77e` | fix(library): retain preset when reselecting filter (#89) | success | [43711305060](https://github.com/SakibShahariar/aniyori/actions/runs/43711305060) |
| `22507208345ae1137d9718ce661031aff7de41a8` | fix(library): clear preset only on filter changes (#89) | success | [43711309585](https://github.com/SakibShahariar/aniyori/actions/runs/43711309585) |
| `33fe3c0c6f660f9a79a14267eb5c914fabf5f513` | test(library): cover unchanged filter preset state (#89) | success | [43711312317](https://github.com/SakibShahariar/aniyori/actions/runs/43711312317) |
| `0079ccd5f59da3e80a35fcac1e5c8d62ce0b67ad` | fix(storage): synchronize explicit episode progress (#24) | success | [43711526489](https://github.com/SakibShahariar/aniyori/actions/runs/43711526489), 471 tests |
| `f947ab3728712243a5aa5963a56ae7f9e124230a` | test(storage): cover aggregate episode state sync (#24) | success | [43711550023](https://github.com/SakibShahariar/aniyori/actions/runs/43711550023), 474 tests |
| `144f472143aed6893e6a78289a63f2338a77adff` | docs(qa): cover aggregate episode state synchronization (#24) | success | [43711725508](https://github.com/SakibShahariar/aniyori/actions/runs/43711725508) |
| `251ce5270044d5e4500ffc59b3401f9c29a96d1c` | test(storage): cover bulk entry episode sync (#24) | success | [43711770577](https://github.com/SakibShahariar/aniyori/actions/runs/43711770577), 475 tests |
| `0dca386db2be0b69232c7708dbf083d21db7c104` | docs(qa): include bulk status episode sync check (#24) | success | [43711866450](https://github.com/SakibShahariar/aniyori/actions/runs/43711866450) |

The two cache-signature failures were caused by a stale unit-test call that passed the raw layout dictionary after the helper contract changed to accept its serialized signature. The follow-up test commit updated the callers in the test and passed. Both failed runs were inspected; they were not hidden or treated as green.

- Previous checkpoint: `f889e2fe5493c1bf2f3613e574180999a9285327`
- Reviewed through: `0dca386db2be0b69232c7708dbf083d21db7c104`
- New checkpoint: `0dca386db2be0b69232c7708dbf083d21db7c104`
- Outstanding: large-library performance benchmark and real GTK checks for layout/preset behavior and episode editor consistency.


### Episode-total reconciliation follow-up — 2026-11-15

The combined-status endpoint returned no status records for these commits. Exact push-triggered workflow runs were retrieved by commit SHA through the Actions API and inspected:

| Commit SHA | Subject | CI result | Run / evidence |
|---|---|---|---|
| `4db32f35c2844e9086723f6e257bd39ef57faa6b` | fix(storage): respect episode totals when syncing progress (#24) | success | [43711985329](https://github.com/SakibShahariar/aniyori/actions/runs/43711985329) |
| `aea573026c25d08ad6744a30d2e21f488c169d1c` | test(storage): cover episode total reduction (#24) | success | [43712012334](https://github.com/SakibShahariar/aniyori/actions/runs/43712012334), 476 tests |
| `3093c365d70a4513f50462235c0004a8768211e5` | docs(qa): cover reduced episode totals (#24) | success | [43712078974](https://github.com/SakibShahariar/aniyori/actions/runs/43712078974), 476 tests |

- Previous checkpoint: `0dca386db2be0b69232c7708dbf083d21db7c104`
- Reviewed through: `3093c365d70a4513f50462235c0004a8768211e5`
- New checkpoint: `3093c365d70a4513f50462235c0004a8768211e5`
- Outstanding: verify episode-editor behavior and reduced-total reconciliation in a real GTK session.
