# Rehearsal — English project description

Current pre-execution impact story, 2026-09-12. Local draft; not submitted. [Form fields](../../submissions/devpost.md) · [Evidence](../test/preflight-impact.md).

## Inspiration

“We leave for our first family camping trip on Saturday. Can you get everything here by Friday evening, for under $200?” A shopping assistant can turn that request into a purchase plan. The important question comes before checkout: what happens if stock disappears, a price changes, or a payment reply never arrives?

Rehearsal measures a plan's effects in isolated virtual environments before it can affect an external transaction. The output is an impact report that helps a person decide whether there is enough evidence to proceed. Consumer shopping assistants such as Rufus inspired the example; this POC does not connect to Amazon or Rufus.

## What it does

The hosted demo freezes a concrete request: one tent and two lanterns, delivered to the family home by Friday at 6 PM, for at most $200 including shipping. If no tent can arrive, do not buy lanterns alone. Prices, inventory and delivery times come from a versioned synthetic catalog.

Amazon Nova 2 Lite proposes a complete-basket plan through Strands tools. Three supplier plans are then run against the same frozen source in twelve isolated simulations: as quoted, A losing tent stock, A increasing its tent price, and an injected missing payment reply. The server completes the full test set even if the model only explores some conditions. Each run executes order, payment and delivery state transitions; the numbers are measured from journals, not predicted in model prose.

A separate verifier recomputes spending, on-time receipts, unresolved reservations and duplicate payments. The English dashboard compares all outcomes and identifies a plan that meets the tested conditions. It stops at the report. Accepting a plan rechecks the source and expiry, then exports an execution brief bound to the selected plan and report hashes. It does not create an Amazon order, authorize a real payment or promise production success.

## How it was built

React and TypeScript run on private S3 behind CloudFront. API Gateway and Lambda admit a bounded request, freeze the source snapshot and start a Step Functions workflow. Amazon Nova 2 Lite runs through Strands on a separate AgentCore preview runtime. Its tools can inspect, propose and simulate; its IAM role cannot invoke the commerce or seller functions or write the commerce table.

Each virtual world has its own state and hash-chained journal in temporary runtime memory. Raw evidence and the provider-usage ledger are exported to S3. A separate Lambda stops the session, independently audits all twelve cells and writes the final report outside the model-writable prefixes. DynamoDB stores source revisions, cost admission, run state and explicit decisions. A source condition check and decision write occur in the same transaction.

There is no always-on application or database server. AgentCore and Lambda execute on demand; S3, DynamoDB storage, logs and service requests remain metered. Each AI run reserves at most $0.50 from the existing finite shared demo allowance. Missing provider usage retains its reservation. Finalized report reads reuse stored evidence rather than making new model calls.

## Challenges

**Measuring consequences:** a fluent explanation is not proof of delivery. We execute a frozen plan and independently replay its journal. Missing, duplicate or corrupted cells block the handoff instead of disappearing from the denominator.

**Payment uncertainty:** in the response-loss simulation, payment commits before the response is hidden. The simulation retains the reservation and queries the same order, avoiding a second authorization. This is an injected virtual transport fault, not a real network-failure experiment.

**Evidence going stale:** a successful simulation can become irrelevant when the source changes. The report carries a source hash and a fifteen-minute validity window. Accepting a different plan, an expired report or changed source fails; duplicate decisions return the original brief without extending its validity.

**Honest scope:** the stock and price shocks target A. B meeting all four conditions does not show that B survives its own disruptions. The report exposes these limits beside the results.

## Accomplishments and results

A real Google Chrome walkthrough exercised the deployed Nova planning, simulation, report, decision export and reload flow. Nova initially proposed A. The independently verified results were:

| Plan | Normal simulated spend | Normal simulated arrival | Tested conditions met |
|---|---:|---|---:|
| A | $149 | Thursday, 6:02 PM | 2/4 |
| B | $179 | Friday, 12:02 PM | 4/4 |
| C | $129 | Monday, 6:02 PM | 0/4 |

The report recommended B for review. Seven actual Nova calls used 16,929 tokens and produced a $0.006197 model-cost estimate from raw provider usage; that is not the final AWS invoice or total infrastructure cost. All twelve exported journals were re-audited locally. The workflow succeeded, the runtime was stopped, the commerce table had zero rows for this preview, and IAM policy simulation confirmed the preview role lacked commerce authority.

The local gate passed 740 Python tests and 28 browser tests. Dedicated checks cover evidence tampering, missing cells, incomplete model usage, retained reservations, idempotent decisions, expiry and a source change between validation and commit. These are implementation checks, not measured user benefit or real-world reliability.

Earlier B0/B1/B2/B3 comparison and Medusa evidence are preserved separately. They do not establish a Peer Review advantage and are not the central claim of this preflight product.

## What was learned

The useful result is not just “the agent can buy.” It is a concrete explanation of the tradeoff before committing: A saves $30 but fails two tested conditions, B fits the deadline in this test set, and C is cheap but late. The person can inspect that evidence, reject the plan or take it into a separately authorized execution process.

## What is next

The next validation is to compare simulation predictions with an independently controlled real execution adapter, then measure whether people make better decisions with the reports. A live catalog connector, production transaction integration, independent held-out scenarios and user-outcome measurements remain future work. This POC provides execution evidence, not a guarantee or a production purchase service.
