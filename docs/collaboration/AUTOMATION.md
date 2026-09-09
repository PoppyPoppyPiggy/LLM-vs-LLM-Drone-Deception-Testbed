# Codex and GitHub automation

## What is configured

- `Offline collaboration CI`: runs on PRs, main/integration/codex pushes, and manual dispatch. It checks collaboration guard tests, inventory consistency, the copied report hash, reporting Python syntax, and whitespace. It executes no experiments or generated reporting code.
- `Codex offline task`: a write collaborator adds the `codex-ready` label to a reviewed Issue or dispatches the workflow with an Issue number. Codex prepares a bounded patch; a separate job enforces path, file-mode, size, and syntax limits and creates one draft PR on `codex/issue-N`. It explicitly dispatches offline CI because pushes made with `GITHUB_TOKEN` do not normally trigger another workflow.
- Task scope: Markdown notes in `docs/collaboration/notes/`, ordinary offline reporting in `scripts/reporting/`, and corresponding synthetic-data tests in `tests/reporting/`. It cannot publish changes to workflows, experiment code, results, or evidence snapshots.
- One generation job per issue group at a time, 15-minute generation timeout, 5-minute publication timeout, no automatic retries, no merge. GitHub may replace an older pending run within a concurrency group; this is not a durable task queue. Existing task PRs/branches cause a stop rather than an overwrite or duplicate PR.

Follow-up on an existing PR uses its exact URL in a local/cloud Codex task. Automatic retry-to-green and arbitrary repository coding are not configured. The scoped workflow does not execute or improve attack agents, live loads, or exploitation. Generated Python requires review before execution.

## Activation that still needs account settings

1. Review and merge the setup PR so event/manual workflows exist on the default branch.
2. In GitHub repository **Settings → Secrets and variables → Actions**, add `OPENAI_API_KEY`. Enter the value directly in GitHub; never paste it into a chat or Issue. The current connector cannot manage repository secrets. The workflow fails explicitly if the key is absent.
3. In **Settings → Actions → General → Workflow permissions**, permit GitHub Actions to create pull requests if account/organization policy permits it. The workflow declares its required job permissions. An organization policy may still prohibit PR creation.
4. Create the `codex-ready` label if absent, then add it to a reviewed, bounded Issue. The initiating actor must have write/maintain/admin permission. Alternatively use **Actions → Codex offline task → Run workflow** with an open Issue number.
5. Inspect the resulting draft PR and the explicitly dispatched offline CI. No real Codex API run was performed while preparing this setup; secret availability and end-to-end task execution are unverified.

Use API project budgets and usage monitoring appropriate to the account. The timeout limits runtime; it is not a guaranteed currency/token cap.

## Cloud/local handoff

On the current local machine, `honeydrone-codex-cloud-watch.timer` is enabled in the user systemd manager. It checks the exact configured task every 15 minutes while that manager is running. The first direct invocation succeeded and retrieved the same 20-file diff. This is read-only monitoring, not a coding loop or a message channel to the cloud conversation.

Private state is stored under `~/.cache/honeydrone-codex-bridge/task_e_6aa119caeb588321b84b8a4b4abfe230/`: `latest.json` records the last check and content-addressed `.patch` files preserve successful downloads. These files are outside Git, are not published automatically, and are never applied or executed by the watcher. Authentication/connectivity failures preserve older snapshots and are recorded as failures. The timer does not work while this machine/user manager is stopped.

```bash
systemctl --user status honeydrone-codex-cloud-watch.timer
systemctl --user stop honeydrone-codex-cloud-watch.timer
# Disable future starts if desired:
systemctl --user disable honeydrone-codex-cloud-watch.timer
```

The installed service points to the clean integration worktree at `/home/user/llm_vs_llm_drone_reconciliation`; update or disable the unit before moving/removing that directory. Its repository configuration is `docs/collaboration/bridge.json`. Existing cloud conversation follow-up remains the owner's action using the prepared prompt; no unsupported private API or token extraction is used.

Use the shared reconciliation Issue and setup PR recorded in `REMOTE_LINKS.md`. The GitHub integration is the common record; it does not synchronize chat history. Before resuming, read the Issue, verify the exact remote branch/SHA, fetch, and inspect the PR diff. Complete one writer's push before the next writer resumes. Keep the original dirty workspace separate from the clean integration worktree.

The exact existing cloud task is readable through authenticated `codex cloud status/diff`; its 20-file diff was retrieved. This does not expose a way to append messages to the same cloud conversation. Use the continuation prompt in `REMOTE_LINKS.md`. The reported Git commit identity remains unverified, and simulation/agent behavior has not been merged.

Official source for the action, its sandbox and credential inputs: https://learn.chatgpt.com/docs/github-action . Publication-job separation follows https://learn.chatgpt.com/docs/non-interactive-mode . Action references are pinned to the commit SHAs resolved from their version tags on 2026-09-10. The action's Codex CLI version uses its upstream default; end-to-end availability must be checked during activation.
