# Cross-workspace reconciliation — 2026-09-10

Repository: https://github.com/PoppyPoppyPiggy/LLM-vs-LLM-Drone-Deception-Testbed

## Verified source identities before this integration branch

| Source | Branch / commit | Verification |
|---|---|---|
| Public GitHub | `main`, `a6f8600f7e69a0897592989315cd6310d2f7f8b8` | Branch API and `git fetch` succeeded. It was the only advertised branch; the PR collection was empty. |
| Local research workspace | `codex-testbed-fixes-v2`, `cdef00033e2d028e61cffc19edf92ba0b828f1f2` | Local commit exists. Workspace is dirty; hierarchical files and pilot outputs are not represented by this HEAD. No published source branch was verified. |
| Exact Codex cloud task | `task_e_6aa119caeb588321b84b8a4b4abfe230`; reported commit `d708b3e` | Authenticated CLI status READY and a 20-file diff retrieved. All 11 existing-file preimage blobs match public main. The abbreviated Git commit itself remains unverified. |

`git merge-base` found no common ancestor between the two available heads. The collaboration branch starts from the verified public main solely to make review possible. This does not select the old public experiment as the authoritative research design.

## File inventory and evidence

`source_inventory.json` records 1,332 selected paths, their local/public SHA-256 hashes, tracked status, and a path-based triage category. There are 41 identical, 25 different, 1,265 local-only, and one public-only entry. This is an inventory, not a complete backup or semantic review. It excludes environments, caches, external repositories, raw traffic, and per-run transcripts. A hash does not publish the corresponding file. `cloud_task_inventory.json` additionally records all 20 paths in the authenticated task diff and their review dispositions.

The original workspace and its results remain in place. No bulk staging, source-history push, force merge, or result replacement was performed.

The local hierarchical pilot report is copied byte-for-byte to `evidence/hierarchical-pilot-20260909.md` with its source path and hash in the inventory. The stored local collection audit reports PASS for 26 runs, and the stored analysis marks confirmatory eligibility false. The experiment was not rerun for this reconciliation. CI verifies the copied report's hash; it does not independently reproduce the pilot.

| Review group | Available evidence | Disposition |
|---|---|---|
| Common/public legacy files | Local files and public Git objects | 41 selected files identical; differing files require review. |
| Shared FANET files | Local/public content hashes | Do not port behavior changes merely because filenames match. |
| Legacy v8 | Local v8 protocol/reports | Keep its null result and protocol separate. |
| Hierarchical L0–L3 | Local protocol, code, pilot JSON and report | Publish the aggregate report and provenance only in this PR. Implementation transfer remains separately scoped. |
| Service diagnostics | Local service/status files | Separate synthetic service quality from swarm outcomes. |
| Cloud dynamic-FANET changes | Authenticated 20-file task diff; 105,424 bytes; SHA-256 in cloud inventory | Governance guidance adapted and original sources archived. Simulation/agent behavior changes are available but deferred to separate scoped review. |

## Conflicting claims to resolve

- “Connected” previously meant repository access, not synchronized source histories. Both source branches are still required for full code reconciliation.
- “PR created” and abbreviated commit hashes in chat are not remote objects without a successful GitHub readback.
- The public main describes legacy experiments. The current local research proposal is hierarchical and has not established LLM/RAG superiority.
- Some local handoff/acceptance sections still call the 26-cell pilot unfinished; the newer pilot report records completion. Preserve dated documents and use an explicit current-status note instead of rewriting frozen evidence.
- Current hierarchical evidence is a functional HTTP emulator pilot, not a flight/RF validation. Do not mix it with v8 or service diagnostics.

## Exact task handoff and reviewed scope

Source task: https://chatgpt.com/codex/cloud/tasks/task_e_6aa119caeb588321b84b8a4b4abfe230

The browser URL redirected to login, but the already-authenticated local CLI succeeded:

```bash
codex cloud status task_e_6aa119caeb588321b84b8a4b4abfe230
codex cloud diff task_e_6aa119caeb588321b84b8a4b4abfe230
```

This retrieves the actual task output without requiring the cloud environment to push. Do not automatically apply the full diff. This connection PR adapts the task's provenance, Issue/PR, baseline-preservation, and evaluation-only-label guidance. Original AGENTS, CONTRIBUTING, and workflow instructions are archived as text and hashed. Current workflows are narrower and do not run the legacy experiment.

All 20 file dispositions are in `cloud_task_inventory.json`. The 11 changed existing files have preimage Git blob IDs matching the public baseline; nine are additions. Task diff access establishes source-content access, not a verified `d708b3e` Git commit or shared chat history.

The original dirty hierarchical workspace remains separate. This PR publishes its aggregate pilot report and source inventory, not its entire codebase. Full simulation/agent code reconciliation is intentionally not part of the documentation/reporting automation setup. Do not import offensive workflows through automated reconciliation.

Continue the same cloud task with the shared Issue and PR URLs in `REMOTE_LINKS.md`. The available CLI can read this task; it does not expose a command to append a message to this existing conversation. The owner can paste the prepared continuation prompt in that exact task. No replacement cloud task was created.
