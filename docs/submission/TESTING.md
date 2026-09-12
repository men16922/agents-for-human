# Test the hosted AWS preflight

Open [the English demo](https://d1u9yhii3gor6j.cloudfront.net). No login or installation is required. One active run shares a finite model allowance.

1. Read the fixed camping request and click **Rehearse this request**. A new admission can incur bounded model charges. A failed start retries the same request ID.
2. Wait for Nova planning and independent verification. Compare all three supplier plans and all twelve condition results.
3. Inspect **A loses tent stock** and **Payment reply lost**. Read spending, receipts, unresolved reservations, duplicates and the coverage limitation.
4. Accept the recommended plan to revalidate the source and record an execution brief, or decline it. Neither creates an external order or payment.
5. Download the brief and raw evidence. Reload the `?preview=...` URL to recover the same result without new model calls. A new acceptance after the fifteen-minute expiry requires a new rehearsal.
6. Optionally select **All tents unavailable** for another paid preview. No plan should be recommended and no lantern-only purchase should appear.

[Actual AWS/Chrome evidence](../test/preflight-impact.md) · [Editable architecture](../../submissions/architecture/rehearsal-serverless.drawio)

For offline preview contracts, run `scripts/dev/with-env.sh uv run --offline --no-sync pytest tests/preflight`. `make check-browser` includes the preview flow with explicitly mocked network fixtures. Those local fixtures do not prove live Nova behavior. The retained Chrome walkthrough uses the actual deployed API and Nova.

The optional local implementation and historical Medusa tests below are separate from the hosted preview. The legacy cloud experiment UI is available at `?legacy=1`; its purchasing experiment scope differs from this simulation-only preview.

# English testing instructions

This is a local test build. Actual Amazon Nova 2 Lite execution and Medusa transactions are recorded; this local path remains separate from the hosted AWS demo, and independent-machine installation remains unverified. Commands use pinned repository runtimes through `scripts/dev/with-env.sh`.

## 1. Install and check

On the verified macOS arm64 platform, install Python 3.12+ for bootstrap, uv 0.11.23, Make and Git. For the independent commerce path, also provide Docker Engine/Desktop and Compose v2. Do not replace credentials belonging to an existing data volume.

From the repository root:

```sh
make setup
make check
make check-browser
```

Setup downloads the pinned runtime, locked dependencies and Chromium. Existing `.env` files are preserved. Later offline checks must fail if dependencies are missing. A green offline gate establishes local code and fixture behavior, not a paid model or cloud deployment.

On 2026-09-12, Linux amd64 container reproduction passed on the same macOS host: Python 663 tests, mypy 57 sources, 25 browser tests, B2/B3 and frozen evaluation, the 80-cell SDK batch, and Medusa backend compilation. The first attempt exposed missing build-only configuration; the corrected script passed in a fresh container with no network or host mounts. This does not establish independent-machine reproduction or Linux Medusa database/HTTP behavior. See [reproduction evidence and commands](../test/linux-reproduction-20260912.md).

## 2. Inspect transaction and review evidence without a paid model

```sh
make world-fixtures
make b2-smoke
make b3-smoke
make pilot-smoke
make frozen-evaluation-smoke
make evaluation-batch-smoke
```

`world-fixtures` verifies normal purchasing, a stale quote, a lost payment response and impossible stock. Its handwritten fixtures are distinct from the B0 pilot.

`b2-smoke` uses one Agent and dialog to open, buy within and close two isolated practice experiments. It proposes a tested policy revision without a separate reviewer. All calls and simulation lifecycle tools share one ledger. This deterministic SDK fixture does not populate the original pilot's B2 cells.

`b3-smoke` runs initial buying, independent review and candidate buying through the Strands SDK with explicit deterministic providers. The output directory contains `usage.sqlite3`, `report.json`, initial/candidate experiments, raw ledger exports, review inputs/responses and policy diffs. Confirm that `scope` is `offline-scripted-model`, `billing_verified` is false and the parent world is unchanged.

`pilot-smoke` freezes a 20-cell roster: five known conditions for each of B0/B1/B2/B3. It executes only B0. Expect four COMPLETE results, one INCOMPLETE result with zero spend, and fifteen NOT_RUN cells. Do not interpret absent model results as failures, successes or zero-cost model runs. No held-out comparison has occurred.

`frozen-evaluation-smoke` connects learning, a frozen policy and a fresh evaluation Agent/world. Learning and evaluation share one budget. All four known-condition paths currently complete at 380 synthetic credits; B1/B2/B3 use deterministic SDK fixtures. This is not a real-model or held-out comparison and does not populate the pilot model cells. See [frozen-evaluation evidence](../test/frozen-model-evaluation.md).

Retained evidence is linked from [B3 accounting](../test/b3-shared-accounting.md) and [current status](../STATUS.md). New runs use ignored `.local/` paths and never overwrite an earlier run. Saved COMPLETE text alone is insufficient; use the raw export and its independent verifier.

`evaluation-batch-smoke` runs a frozen roster of 20 known conditions × four arms, with one repetition. The durable batch budget reserves each model cell before admission. Interrupted or unknown-usage cells hold their remaining reservation and stop further admissions. Reports retain missing, failed and invalid cells in the denominator. The preserved 80-cell run uses SDK fixtures; it is not a held-out or real-model comparison. See [batch evidence and limits](../test/evaluation-batch.md).

For a practice batch's token and elapsed-time comparison, run:

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.evaluation.metrics .local/evaluation/<batch-directory>
```

Add `--format json` for machine-readable metrics. The report reaudits artifacts, includes learning and evaluation tokens, retains every planned cell, and shows the sample count for each metric. New uninterrupted cells record monotonic total execution time; historical cells without that record have unavailable timing. Failed attempts remain in the denominator. These are not provider-latency, recovery-time or model-efficacy measurements. See [verification and scope](../test/evaluation-metrics.md).

## Inspect retained actual Nova results without AWS calls

The repository includes [actual practice/review/pilot results](../test/nova-live.md) and [actual stock-change runs with browser/video evidence](../test/nova-reactive-video.md). The latter retains two successful deliveries and one failed deadline run. These are separate from the deterministic commands above.

```sh
scripts/dev/with-env.sh uv run --offline --no-sync python -m rehearsal.evaluation.metrics evidence/cw03-nova-live/pilot-02
```

This command reaudits the retained 20-cell roster and reports 4/5 B0, 3/5 B1, 3/5 B2 and 4/5 B3 goal completions, with USD0.515321 of recorded model usage. It creates no AWS client and makes no paid call. The [3:45 English actual-Nova video](../../evidence/cw08-nova-final-video/rehearsal-draft.mp4) has narration and subtitles. Keep its independent verdict, failed-run description and the distinction from the original SDK video visible when demonstrating the project.

## 3. Open the observer UI

```sh
make dev
```

Open `http://127.0.0.1:15173`. Without a configured observer run, expect the unconfigured state. No purchase is started by opening this page. Ctrl+C stops the owned API and web processes. Do not run the browser gate concurrently on the same ports.

For an automated real Medusa observer test, stop `make dev`, start `make commerce` in terminal A, wait for readiness, then run the following in terminal B:

```sh
make commerce-observer-smoke
```

The smoke creates isolated synthetic commerce data, runs a browser walkthrough and retains its logs/screenshots. Inspect its printed evidence directory and independent COMPLETE/observation comparison. It tests a scripted recovery path; it does not initialize a real model. In terminal A, use Ctrl+C after the smoke finishes to stop Medusa and its dedicated database containers. Keep the data volumes.

To inspect the execution's decisions alongside live transaction observations, use this newer walkthrough with Medusa ready:

```sh
make commerce-reaction-ui-smoke
```

For a view that stays open after the automated walkthrough, run `make commerce-demo` instead. Wait for **Inspection ready**, open `http://127.0.0.1:15173`, and inspect delivery, blocked actions and independent evidence. Reloading the page reconnects to the same live run. Ctrl+C ends the inspection and exports final evidence; stop the separate `make commerce` terminal afterwards. This is an explicitly scripted SDK buyer, with no paid model calls. The [inspection test](../test/demo-inspection.md) verified a separate desktop/mobile browser and shutdown. A make process interrupted by Ctrl+C may return a nonzero shell status; inspect the final session/evidence and owned-service cleanup separately.

It starts a known Strands SDK buyer, the local API/web servers and Chromium. Expect A stock 10→0, a blocked stale A order, one B order/payment, delivery of three tents and six lights for 380 credits, and provisional→sealed execution records. It then checks a separate raw export in the browser and again after session shutdown. The [retained live run](../test/execution-reaction-ui.md) has screenshots, request records and both independently reverified exports. No browser responses are mocked in this command. The ordinary browser regression suite also contains explicitly mocked/replayed cases.

Run these walkthroughs sequentially: they share ports 18000/18001/15173 with the development UI and browser gate. Each smoke stops its own session/API/web/browser; stop terminal A separately to stop Medusa/PostgreSQL/Redis. A stopped process does not imply a completed transaction or release an uncertain payment reservation.

For a manually selected execution, set `REHEARSAL_OBSERVER_CONFIG`, `REHEARSAL_EXECUTION_CONFIG` and optionally `REHEARSAL_EVIDENCE_CONFIG` before `make dev`. The execution selection contains only `run_id`, `expected_goal`, `expected_budget`, `execution_path` and the exact `spec_sha256`. Paths are server-side local settings, never browser inputs. Use the [selection schemas](../test/execution-reaction-ui.md) and [independent export schema](../test/independent-evidence-ui.md). The UI compares run/goal/budget, reads every two seconds and removes old execution counts after a failed or timed-out refresh. A terminal file hash check is distinct from an independent transaction verdict.

## 4. Check independent HTTP contracts

With `make commerce` running in terminal A, run this separately in terminal B:

```sh
make commerce-contract
```

This creates synthetic test orders and checks authorization, payment, fulfillment and delivery responses. Each run adds local test data. No real funds are involved. `commerce-smoke` alone only checks service readiness and is not a substitute for the transaction contract test.

With Medusa active, `make commerce-model-smoke` checks a metered Strands buyer using a deterministic SDK provider against real loopback Medusa. It keeps runtime completion separate from a later independent export/created-order attestation. This is not a real-model transfer result. See [metered HTTP evidence](../test/metered-http-model.md).

With the same service ready, run `make external-reaction-smoke` for the four-arm integration check. It prepares a separate known-condition roster, learns where required, freezes policy and reaction settings, then creates a fresh Medusa session for each cell. B0 reactions are disabled; B1/B2/B3 share the declared replan limit. B2/B3 preserve learning call rows and limits in the external execution ledger. Inspect transaction, initial/scheduled-condition, reaction-integrity and usage results separately. The [retained 4/4 run](../test/frozen-reaction-comparison.md) is a scripted integration check, not a real-model performance ranking, and leaves the original pilot unchanged.

## 5. Optional real model test

Configure `AWS_PROFILE`, `AWS_REGION`, `REHEARSAL_MODEL_ID`, the model budget, all four token rates and `REHEARSAL_RATE_SOURCE` in the ignored `.env` or the process environment. Confirm the model's official current rates and intended spending scope first.

```sh
make agent-preflight  # Settings only; no AWS client
make agent-run        # Explicit paid model invocation
```

A missing-setting error is expected until the model configuration is provided. Each provider call reserves an estimated amount and token allowance. Raw usage omission leaves an unresolved reservation and blocks later calls. The cap is an admission estimate, not a guarantee of the final invoice.

For the independent Medusa path, the [session CLI](../test/model-session.md) keeps the seller/gateway alive, hands off a private buyer-only config, and exports evidence on shutdown. Session creation invokes no model. Paid HTTP execution remains an explicit separate `model_runner --execute` command, and independent attestation is distinct from runtime completion.

Prepare model settings and freeze learning evidence before starting a session: its real-time deadline keeps advancing. A direct reactive HTTP execution accepts `--max-replans` (1–32). A frozen external batch accepts that option only at `external_batch --prepare`; `--learn` and `--execute` cannot change it. Preparation writes local state without a model/HTTP call; learning and execution are separate paid operations for model arms. `--settle` performs independent evidence checks and updates the batch reservation state; `--report` is read-only. Follow the [external batch procedure](../test/external-comparison-budget.md) and [reaction settings contract](../test/frozen-reaction-comparison.md). Do not reuse a learning policy without its original usage ledger or silently increase a frozen budget.

## Limitations when judging

Only the stated local scopes are verified. Actual Nova replanning succeeded in two stock-change schedules and failed in another. Browser evidence alone does not establish model quality, the overall latency target or cross-device behavior. Known scripted executions do not establish model transfer. The two small real-model pilots show no Peer Review advantage. A separate frozen 20-condition batch and a post-prompt known pilot are now [recorded](../test/nova-delivery-prompt.md). Independent held-out generalization, developer observations, public repository/video/access and the final submission remain pending. Report failures with the command and printed evidence directory, never by sharing `.env`, credentials or database secrets.
