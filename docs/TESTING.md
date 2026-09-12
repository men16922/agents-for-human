# Testing

## Hosted preview

Open [the AWS demo](https://d1u9yhii3gor6j.cloudfront.net). No login is required; new runs consume a finite shared model allowance.

1. Keep the camping scenario selected and click **Rehearse this request**.
2. Wait for Nova planning and independent verification; compare all three plans and twelve conditions.
3. Inspect **A loses tent stock** and **Payment reply lost**, including spending, receipts, unresolved reservations and duplicates.
4. Decline or accept an eligible plan for execution review. Acceptance rechecks the source and evidence expiry; it creates no external order.
5. Download the brief and raw evidence, then reload the preview URL. The stored result is reused without a model call. A new acceptance needs evidence within fifteen minutes of snapshot capture.

The optional **All tents unavailable** case starts another paid preview. It should recommend no plan and make no lantern-only purchase. Nova’s initial proposal can vary on a new run.

## Local checks

After [setup](DEVELOPMENT.md):

```sh
make check
make check-browser
scripts/dev/with-env.sh uv run --offline --no-sync pytest tests/preflight
```

The offline gate checks documentation, installed tools, locks, lint, types, Python behavior and the web build. Browser fixtures and SDK fixtures are explicit; neither proves live model efficacy.

Additional commands retained for the local commerce/evaluation modules include `make world-fixtures`, `make b2-smoke`, `make b3-smoke` and `make evaluation-batch-smoke`. They write fresh artifacts under `.local/` and use known scenarios. With Medusa running, `make commerce-contract` checks actual local HTTP ownership, order and payment behavior using synthetic funds.

Keep failures, missing usage and unresolved reservations explicit. Payment authorization, delivery and orchestration completion are different states. Results and limitations are summarized in [VERIFICATION.md](VERIFICATION.md).
