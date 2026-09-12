# Verification

## Recorded AWS demonstration — September 12, 2026

Run `preview-ed7060a53bc676ce628912b90c666ae9` used actual Nova 2 Lite through Strands and the deployed Chrome dashboard. Its commerce catalog and delivery schedules were synthetic.

| Plan | Normal simulated spending | On-time conditions met |
|---|---:|---:|
| A, initial proposal | $149 | 2/4 |
| B, report recommendation | $179 | 4/4 |
| C | $129 | 0/4 |

All twelve exported cells were independently reverified. Nova used seven calls, 16,422 input tokens and 507 output tokens; the ledger estimated $0.006197 in model cost. This excludes infrastructure and is not a reconciled AWS invoice.

The preview had zero commerce-table rows. Step Functions succeeded, runtime termination was independently checked, and IAM policy simulation verified the preview role’s commerce restrictions. Chrome covered report detail, decision export, reload and mobile layout.

The recorded pre-cleanup gates passed 740 Python tests and 28 browser tests. Two browser tests covered the subsequently removed illustrative HTML proposal; the application test remains. Current commands are documented in [TESTING.md](TESTING.md).

## Source-only cleanup checks

After cleanup, the 296 tracked files were copied without root evidence, submission drafts or local agent configuration. Using existing pinned dependencies on the same machine, the copy passed `make check`: 740 Python tests, mypy for 75 source files, lint, locks, documentation and web build. The separate local browser suite passed 26 tests. Two obsolete HTML-proposal tests were removed; all application checks were retained. This was not a fresh dependency installation or an independent-host reproduction.

## Evidence location

Raw logs, database snapshots, recordings and superseded audit documents were removed from the working tree at the user’s request. A small required subset was moved to `tests/fixtures/` for regression tests; the full directory is not a runtime dependency. The already-published commit preserves the original records:

- [Full preflight audit](https://github.com/men16922/agents-for-human/blob/6967eba/docs/test/preflight-impact.md).
- [Run audit and model-cost summary](https://github.com/men16922/agents-for-human/blob/6967eba/evidence/preflight/preview-ed7060a53bc676ce628912b90c666ae9/audit.json).
- [Raw run evidence](https://github.com/men16922/agents-for-human/tree/6967eba/evidence/preflight/preview-ed7060a53bc676ce628912b90c666ae9).

New local artifacts belong in ignored `.local/`; deployed runs export to S3. Submission media remains local and excluded from Git.

## Limits

The stock and price shocks target A. The counts are not success probabilities, and payment response loss is an injected simulation fault. No live Amazon/Rufus connector, real payment authorization, production prediction accuracy or measured user benefit is claimed. SDK fixtures establish implementation behavior, not model superiority. Earlier Medusa/evaluation code remains for regression and reproduction; its existence does not establish learned-policy transfer.
