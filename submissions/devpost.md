# Rehearsal — Devpost submission draft

Updated September 12, 2026 for the deployed preflight workflow. Copy each field separately into Devpost. Items marked **Pending** are preparation notes, not form values. Implementation claims are checked against the [preflight audit](../docs/test/preflight-impact.md). This is a local draft; do not submit.

## Project overview

### Project name

Rehearsal

### Elevator pitch

See the impact before an AI agent acts. Rehearsal simulates transaction plans, measures costs and risks, and gives people evidence to decide whether to proceed.

## Project details — public project page

### About the project

Copy the story between the markers into **About the project**.

<!-- BEGIN PROJECT STORY -->

## Inspiration

“We leave for our first family camping trip on Saturday. Can you get everything here by Friday evening, for under $200?” A shopping assistant can turn that request into a purchase plan. The important question comes before checkout: what happens if stock disappears, a price changes, or a payment reply never arrives?

Rehearsal is for people deciding whether to trust an agent with a transaction. It runs the proposed plan in isolated virtual environments and measures the consequences before an external order or payment can happen. The result is an impact report: what the plan spends, whether it meets the deadline, where it fails, and which alternative meets the tested conditions. Consumer shopping assistants such as Rufus inspired the example; this POC uses a synthetic catalog and has no Amazon or Rufus connection.

## What it does

The demo starts with one concrete request: one tent and two lanterns, delivered to the family home by Friday at 6 PM, for at most $200 including shipping. If no tent can arrive, do not buy lanterns alone.

1. **Freeze the request and source.** Capture the catalog's prices, stock and delivery schedule, together with the shopper's budget, quantities, destination and deadline.
2. **Propose a plan.** Amazon Nova 2 Lite uses Strands tools to inspect that snapshot, propose a complete-basket plan and rehearse it.
3. **Measure alternatives.** Execute three supplier plans across four conditions in twelve isolated worlds: as quoted, A losing tent stock, A increasing its tent price, and an injected missing payment reply. The server completes the full test set even if the agent explores only some conditions.
4. **Show the impact.** An independent verifier replays each journal to calculate spending, on-time receipts, unresolved reservations and duplicate payments. The dashboard compares every result and exposes the tested coverage.
5. **Stop for a decision.** The person can decline or accept a qualifying plan for execution review. Acceptance rechecks the source and report expiry, then records a downloadable brief bound to that exact plan and report. It does not place an external order or authorize a real payment.

The reported numbers come from executed order, payment and delivery state transitions. They are measured simulation outcomes, not estimates generated in the model's answer.

## Why it matters

A low price alone does not answer the family's question. A basket that arrives on Monday misses the trip; lanterns without a tent do not satisfy the request. Rehearsal brings these consequences into the decision before money is committed.

Its intended benefit is a more informed choice about whether and how an agent should act. The current demo shows a concrete tradeoff and the evidence behind it. Reduced financial losses, time savings and improvements in user decision quality have not yet been measured.

## How it was built

React and TypeScript run on private S3 behind CloudFront. API Gateway and Lambda admit a bounded request, freeze the source snapshot and start a Step Functions workflow. Amazon Nova 2 Lite runs through Strands on a separate AgentCore preview runtime. Its tools can inspect, propose and simulate; its IAM role cannot invoke the commerce or seller functions or write the commerce table.

Each virtual world has its own state and hash-chained journal in temporary runtime memory. Raw evidence and the provider-usage ledger are exported to S3. A separate Lambda stops the session, independently audits all twelve cells and writes the final report outside the model-writable prefixes. DynamoDB stores source revisions, cost admission, run state and explicit decisions. A source condition check and decision write occur in the same transaction.

There is no always-on application or database server. AgentCore and Lambda execute on demand; S3, DynamoDB storage, logs and service requests remain metered. Each preview reserves $0.50 from the existing finite shared model allowance before it starts. Missing provider usage retains its reservation. Finalized report reads reuse stored evidence rather than making new model calls.

## Challenges

**Measuring consequences:** a fluent explanation is not proof of delivery. We execute a frozen plan and independently replay its journal. Missing, duplicate or corrupted cells block the handoff instead of disappearing from the denominator.

**Payment uncertainty:** in the response-loss simulation, payment commits before the response is hidden. The simulation retains the reservation and queries the same order, avoiding a second authorization. This is an injected virtual transport fault, not a real network-failure experiment.

**Evidence going stale:** a successful simulation can become irrelevant when the source changes. The report carries a source hash and a fifteen-minute validity window. A plan without qualifying evidence, a report that has expired, or a source that has changed cannot receive a new execution brief. Duplicate decisions return the original brief without extending its validity.

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

## What was learned

The most useful output was the tradeoff before committing: A saves $30 compared with B but fails two tested conditions; B fits the deadline in this test set; C is cheap but late. Freezing the plan and keeping its evidence separate from the final decision makes that choice inspectable. The person can reject it or take the brief into a separately authorized execution process.

## What is next

The next validation is to compare simulation predictions with an independently controlled real execution adapter, then measure whether people make better decisions with the reports. A live catalog connector, production transaction integration, independent held-out scenarios and user-outcome measurements remain future work. This POC provides execution evidence, not a guarantee or a production purchase service.

<!-- END PROJECT STORY -->

### Built with

Use these 16 tags, within the form's 25-tag limit:

```text
Amazon Bedrock, Amazon Nova 2 Lite, Strands Agents SDK, Amazon Bedrock AgentCore, AWS Lambda, Amazon API Gateway, Amazon DynamoDB, Amazon S3, Amazon CloudFront, AWS Step Functions, Python, FastAPI, React, TypeScript, SQLite, ElevenLabs
```

ElevenLabs Daniel narrates the English submission video. The planning model is Amazon Nova 2 Lite.

### Try it out links

| Field | Value / action |
|---|---|
| Public source repository | **Pending publication/access verification:** configured Git origin is `https://github.com/men16922/agents-for-human`. Enter it only after the current source is published and anonymous access is checked. |
| Demo site or application | https://d1u9yhii3gor6j.cloudfront.net — English demo; no login required; finite shared run allowance. |

Do not enter localhost addresses or filesystem paths into these public link fields.

## Project media

### Image gallery

The following files are local upload candidates, not public URLs:

| Asset | Local file | Caption |
|---|---|---|
| Request | [overview.png](../evidence/preflight/chrome/overview.png) | One tent, two lanterns, a $200 budget and a Friday deadline. Rehearse before placing an order. |
| Live AWS dashboard | [result.png](../evidence/preflight/chrome/result.png) | Actual Nova preview: three plans, twelve virtual runs, independently verified impact report. |
| Payment evidence | [payment-detail.png](../evidence/preflight/chrome/payment-detail.png) | Inspect a simulated lost payment reply, same-order reconciliation and zero duplicate payments. |
| Decision | [decision-after.png](../evidence/preflight/chrome/decision-after.png) | A recorded execution-review brief, with the source and report hashes. No external order was placed. |
| Architecture | [rehearsal-serverless.png](architecture/rehearsal-serverless.png) | Deployed AWS serverless preview, evidence and decision paths. |

The architecture also has an editable [draw.io source](architecture/rehearsal-serverless.drawio) with two pages. These are actual deployment materials; earlier local screenshots remain in historical evidence.

### Video demo link

**Pending:** provide a public YouTube or Vimeo URL after the final edit is uploaded.

Local materials:

- [2:53 English Chrome demo video](video/rehearsal-demo.mp4), 1080p with 28 English captions: visible Chrome walkthrough of Nova planning, isolated simulations, impact comparison, payment evidence, explicit decision and reload; Daniel narration and English captions.
- [English SRT subtitles](video/captions.en.srt) and [thumbnail](video/thumbnail.png).
- [YouTube title, description and chapters](video/youtube.md); [production and verification record](../docs/test/preflight-impact.md).

## Additional info — judges and organizers

### Submitter Type

**Pending entrant confirmation.** Select the appropriate individual/team or organization option offered by the form.

### Country of Residence

**Pending entrant confirmation.** Select the entrant's actual country of residence. A browser profile name or language is not sufficient to fill this field.

### Organization name

Leave blank if not submitting on behalf of an organization. Otherwise use the entrant-confirmed organization name.

### Track

**Everyday Agents** — recommended for the current family-shopping decision scenario. This is a local draft recommendation; the Devpost form has not been changed. The [official track description](https://agentsforhumans.devpost.com/) covers daily life and family errands.

### Public URL to code repository

**Pending publication and anonymous-access verification.** Configured Git origin: `https://github.com/men16922/agents-for-human`.

Publish the current preflight implementation, required assets, setup instructions, README and MIT license before using this as the submission URL. Earlier source packages predate the current report-and-decision workflow.

### Architecture diagram

Upload [rehearsal-serverless.png](architecture/rehearsal-serverless.png). The [architecture explanation](../docs/submission/ARCHITECTURE.md), [editable draw.io](architecture/rehearsal-serverless.drawio) and [SVG](architecture/rehearsal-serverless.svg) accompany it.

### AWS Builder ID

**Pending entrant-provided AWS Builder ID.** Do not substitute an AWS account ID, access key, Chrome profile name or Devpost username.

### Optional live demo URL

https://d1u9yhii3gor6j.cloudfront.net

### Testing instructions for application

Copy the following instructions into the application testing field:

> Open https://d1u9yhii3gor6j.cloudfront.net. No login or installation is required. The fixed camping request uses synthetic prices, inventory and delivery times; it has no Amazon connection.
>
> Leave Camping essentials available selected and click Rehearse this request. The finite shared allowance permits one active run. Nova proposes a plan, twelve isolated simulations execute, and a separate verifier builds the report. A busy or exhausted allowance rejects a new start.
>
> Compare all three plans. In the retained demonstration, normal simulated spending is A $149, B $179 and C $129, with 2/4, 4/4 and 0/4 tested conditions met respectively. Nova's initial proposal may vary on a new run. These are results for the fixed test set, not real-world success probabilities.
>
> Click A: A loses tent stock to inspect the blocked purchase. Click B: Payment reply lost to inspect same-order reconciliation, spending and duplicate-payment counts. Read the coverage limitation: stock and price shocks target A; B's own disruptions are not tested.
>
> Select Accept plan B & export brief to recheck the source and report expiry, or Decline these plans. Acceptance records evidence for execution review; no external order or real payment is created. Download the decision brief and raw evidence, then reload the preview URL to recover the same decision without another model run. New acceptance requires an unexpired report; replaying a recorded brief does not renew it.
>
> Optional: select All tents unavailable and run a new rehearsal. This starts another bounded model run. No plan should be recommended, and no lantern-only purchase should occur. Local reproduction and retained AWS evidence are documented in docs/submission/TESTING.md and docs/test/preflight-impact.md.

### Optional Bonus Blog Post URL

Leave blank. No bonus post has been published on builder.aws. If one is prepared, use a title containing “Agents for Humans” as required by the supplied form.

## Final draft review — preparation notes, not form content

- Project name is within 60 characters; elevator pitch is within 200 characters; the technology list has fewer than 25 tags.
- The public story reports the measured preview results and preserves the synthetic-world and coverage limits.
- Hosted AWS/Chrome verification is recorded in the September 12 preflight audit. Public repository/video access and entrant identity/Builder ID remain pending.
- The English dashboard, 2:53 Daniel-narrated video, 28 captions and two-page AWS diagram reflect the same preflight workflow. Public code/video publication remains pending.
- Historical B0/B1/B2/B3 and Medusa results are preserved separately; they do not establish Peer Review superiority or production reliability.
- Save draft changes only. **Do not click Submit.**
