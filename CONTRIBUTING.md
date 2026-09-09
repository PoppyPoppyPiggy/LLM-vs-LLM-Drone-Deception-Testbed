# Contributing

Record the repository URL, source branch, full HEAD SHA, dirty status, protocol, and evidence paths in the linked Issue. A dirty workspace needs file hashes as well as its HEAD SHA.

Work on a branch from a verified remote base. Stage explicit paths only. Preserve raw evidence and separate protocol lineages. Read `docs/collaboration/RECONCILIATION.md` for the current missing source.

Run these dependency-free, offline checks from the repository root:

```bash
python3 -m unittest discover -s tests/collaboration -v
python3 scripts/collaboration/check_repository.py
git diff --check
```

These checks validate collaboration metadata and Python syntax. They do not run the legacy experiment, reproduce the hierarchical pilot, or validate a protection claim.

For an automated documentation/reporting task, create an Issue with a precise result and add `codex-ready` after reviewing it. See `docs/collaboration/AUTOMATION.md` for activation and allowed paths. Agent-generated Python is syntax-checked and reviewed before execution; it is not executed by the publication job.
