# Rehearsal

**See the impact. Then decide.** Rehearsal executes an agent's transaction plan in isolated virtual worlds, measures its consequences, and presents the evidence before an external transaction can happen.

[Open the AWS demo](https://d1u9yhii3gor6j.cloudfront.net) · [Chrome demo video](submissions/video/rehearsal-demo.mp4) · [Editable AWS draw.io](submissions/architecture/rehearsal-serverless.drawio) · [Verification](docs/test/preflight-impact.md)

A family leaves for a camping trip Saturday: one tent and two lanterns, at home by Friday evening, for at most $200 including shipping. Nova proposes a plan. Three suppliers are compared across twelve isolated runs. The report measures spending, on-time delivery, unresolved payments and duplicates, then stops for an explicit decision.

In the retained actual Nova/Chrome preview, A was the initial proposal ($149, 2/4 tested conditions met), B was recommended for review ($179, 4/4), and C missed the deadline ($129, 0/4). Stock and price shocks target A; these counts are not success probabilities. All transactions use a synthetic catalog. There is no Amazon/Rufus integration or real payment service.

Accepting rechecks the source revision and fifteen-minute report expiry, and records a brief bound to the chosen plan and report hashes. It creates no external order. Evidence survives runtime shutdown; reading a stored report does not call the model again.

The English UI uses CloudFront/private S3. API Gateway and Lambda start a bounded Step Functions preview. Nova 2 Lite runs through Strands on a separate AgentCore role with no commerce invocation or commerce-table write permission. A separate Lambda verifies raw journals, stops the runtime and exports the report. DynamoDB holds source revisions, admission and decisions. Storage and requests remain metered. [Deployment guide](infra/serverless/README.md).

[Architecture and boundaries](docs/submission/ARCHITECTURE.md) · [Testing](docs/submission/TESTING.md) · [Devpost draft](submissions/devpost.md) · [Status (Korean)](docs/STATUS.md)

## Run locally

Verified platforms: macOS arm64 and Linux amd64 in a container on the same Mac ([Linux evidence](docs/test/linux-reproduction-20260912.md)). A clean independent-machine installation and Linux Medusa database/HTTP execution remain unverified. Prerequisites: Python 3.12+ for bootstrap, uv 0.11.23, Make and Git. Docker with Compose v2 is needed only for Medusa. Node and the project Python runtime are installed into this repository.

```sh
make setup          # Explicit network installation; does not call a model
make check          # Offline dependencies, types, tests, documentation and web build
make check-browser  # Separate local browser gate
make dev            # API and observer UI; Ctrl+C stops both
```

Open `http://127.0.0.1:15173`. Without an observer run connection the UI shows its unconfigured state. `make dev` does not create commerce orders or initialize a paid model. See [testing instructions](docs/submission/TESTING.md) for a real Medusa browser walkthrough.

## Earlier transaction-agent evidence

```sh
make world-fixtures  # Known local ledger cases; no model
make policy-smoke    # Scripted fork, counterexample and policy diff
make b2-smoke        # One Strands Agent explores two isolated practice experiments
make b3-smoke        # Real Strands SDK with deterministic provider fixtures
make pilot-smoke     # Five known B0 cases; unexecuted B1/B2/B3 cells stay visible
make frozen-evaluation-smoke # Known learning/freeze/evaluation composition; SDK fixtures
make evaluation-batch-smoke # 20 known conditions × four arms; SDK fixtures
```

Each command prints its evidence directory under ignored `.local/`. B3 accounts for initial buying, review, and candidate buying in a shared durable ledger. Missing provider usage retains reservations and blocks subsequent calls. The pilot freezes its cases, policy and execution sources before running. It preserves incomplete, interrupted, invalid and absent results in the denominator. These are plumbing and known-case checks, not a model benchmark.

To exercise the independent backend, run `make commerce` in one terminal and `make commerce-contract` in another. These commands create synthetic test orders in the dedicated `rehearsal-dev` project. No real funds or payment provider is used. Ctrl+C in the first terminal stops owned services and preserves volumes. Further examples are in [English testing instructions](docs/submission/TESTING.md).

With Medusa ready, `make commerce-reaction-ui-smoke` runs a known SDK buyer and a real browser together. A scheduled stock reduction invalidates an earlier decision; the wrapper blocks the stale order, the scripted buyer requests supplier B, and the browser shows delivery and a separate independent export verdict. The [retained run](docs/test/execution-reaction-ui.md) delivered three tents and six lights for 380 credits, with five recorded replans and one blocked action. This is scripted recovery, not measured model judgment.

To inspect the verified live view yourself, keep `make commerce` running in terminal A and run `make commerce-demo` in terminal B. After **Inspection ready**, open `http://127.0.0.1:15173`. The page stays available for reloading and independent evidence checks until Ctrl+C in terminal B. Then stop terminal A separately. This creates local synthetic commerce data with a deterministic SDK buyer and makes no paid model calls. See the [tested inspection workflow](docs/test/demo-inspection.md).

`make external-reaction-smoke` exercises the separate four-arm Medusa roster. B2/B3 carry their learning usage into the external execution ledger; the batch keeps all planned cells and unresolved reservations. Reaction settings are frozen before learning, with B0 disabled and identical limits for B1/B2/B3. See the [known four-arm results and limits](docs/test/frozen-reaction-comparison.md).

## Evidence boundaries

| Evidence | What it establishes | What remains open |
|---|---|---|
| Local raw ledger verification | Goal, spending, reservations and delivered inventory can be audited independently | Real-world financial safety |
| Actual Nova 2 Lite practice and Medusa execution | Normal goal COMPLETE 310, frozen policy handoff, original provider usage and independent external attestation | Learned-policy improvement, held-out generalization and final AWS billing reconciliation |
| SDK purchasing/review fixtures | Tool boundaries, fork linkage and shared accounting execute through Strands | Real model decisions and review efficacy |
| Medusa HTTP and independent seller | Synthetic orders, delivery, ownership/run checks and recovery | Learned policy transfer and distributed races |
| Live SDK/Medusa and browser | Stock changes, stale-action blocking, delivery, provisional/sealed execution records and separate export verification | Overall latency target and real-model replanning |
| Five-case B0 pilot | Four COMPLETE, one INCOMPLETE; fifteen model cells remain NOT_RUN in that original roster | Separate Nova pilots are recorded above; held-out comparison remains |
| Separate frozen four-arm Medusa run | Four known executions, checked conditions and shared learning/execution costs | Learned-policy or Peer Review efficacy; scripts and timing do not provide a fair performance comparison |

A payment approval is not a delivery. An HTTP timeout does not prove rollback. A provider-usage omission is not zero cost. A preserved success report is not sufficient evidence: the verifier recomputes from exported ledger rows.

## Paid model execution

`make agent-preflight` checks explicit model, region/profile, rates and spending limits without constructing an AWS client. `make agent-run` invokes the configured paid model. The offline commands above do not require AWS credentials. Rates must be confirmed for the chosen model; admission estimates do not guarantee the final provider invoice. B3 additionally shares total token and tool-call admission across roles.

## Repository and provenance

- `src/rehearsal/`: world, independent verifier, commerce gateway, Strands execution and evaluation.
- `src/rehearsal/preflight/`: frozen requests, simulation, independent impact reports and decisions.
- `web/`: hosted preflight UI and local read-only observer; `services/medusa/`: optional local backend.
- `infra/serverless/`, `src/rehearsal/serverless/`: deployed AWS templates and runtime.
- `scenarios/`, `tests/`, `evidence/`: known cases, executable checks and retained evidence.
- `docs/submission/`: English local review package and [current video script](docs/submission/VIDEO_SCRIPT.md). The AWS demo is deployed. Public repository/video upload and final submission remain pending.
- `agents-for-human-propsal.html` and `assets/proposal/`: illustrative proposal scenes and generated concept images, not product screenshots.
- `archive/`: superseded Aftercare/BillBuddy proposals, not the current product requirements.

Original project source is [MIT licensed](LICENSE); dependencies retain their own licenses. See [third-party notices](THIRD_PARTY_NOTICES.md). Do not publish `.env`, `.tooling`, `.venv`, local databases, credentials, service logs or dependency directories. The private sibling project is not incorporated.

The optional overnight runner comes from an installed plugin. It is not needed to run the product. No unattended seeds are active; normal commands do not commit, push, publish or deploy.
