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
- Checkpoint SHA: `12ffcfc1ebc4e9373283a93a92d3d4e6b546d774`
- Initialized: 2026-11-02
- Baseline: latest branch tip queried through combined commit-status endpoint; empty status list recorded as **unavailable**, not green/red. Older history was not retroactively audited during setup.
- Next session: review commits after `12ffcfc1ebc4e9373283a93a92d3d4e6b546d774`; carry forward any red or unresolved entries.

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

