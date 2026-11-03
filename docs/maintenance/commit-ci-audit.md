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
- Checkpoint SHA: `2a39e57eec14278e5282f5ee80368d5d181b7b4c`
- Initialized: 2026-11-02
- Baseline: latest branch tip queried through combined commit-status endpoint; empty status list recorded as **unavailable**, not green/red. Older history was not retroactively audited during setup.
- Next session: review commits after `2a39e57eec14278e5282f5ee80368d5d181b7b4c`; carry forward any red or unresolved entries.

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
