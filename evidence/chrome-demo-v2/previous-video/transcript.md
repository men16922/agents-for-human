# Rehearsal — AWS demo transcript

English narration: ElevenLabs Daniel. Actual AWS recording at original speed.

## 00:00 — A payment is not a delivery.

A purchasing agent can finish its answer while the goods are still missing. Rehearsal gives developers and quality assurance teams a controlled place to test that gap. Change inventory or prices, inspect the agent's actions, and verify delivery against independent transaction records.

## 00:24 — A live demo without an always-on server.

The English dashboard is hosted on CloudFront and private S3. An API starts a bounded workflow. Amazon Nova two Lite runs through Strands on AgentCore. Lambda and DynamoDB hold the commerce records, while Step Functions advances the seller independently. The runtime session is stopped after the audit. Storage and requests still incur usage charges.

## 00:55 — Practice and review are testable choices.

B zero uses a fixed rule. B one buys directly with Nova. B two lets one agent practice before entering the live world. B three adds an independent reviewer with no purchasing tools. Practice, review, and live buying share one usage ledger. These options let us measure the cost of extra reasoning.

## 01:21 — Nova handles disappearing stock on the deployed system.

This recording runs at original speed. Supplier A loses its tents after the purchase clock starts. Nova chooses supplier B. Watch the payment reservation, the actual delivery count, and the separate verification result. The agent's final answer is not the completion authority.

## 02:07 — The journal confirms delivery.

The independent audit confirms three tents and six lights, delivered on time for 380 credits, with no unresolved payment reservation. This run used 9 model calls and less than one cent of estimated model usage. The workflow succeeded, and a separate check confirmed that its runtime session was no longer present.

## 02:35 — More agents did not automatically win.

An earlier frozen comparison included twenty conditions per method. The rule baseline completed fifteen goals. Direct Nova completed eleven, simulation completed eight, and peer review completed seven. Different starting policies and one execution per condition limit the comparison. These historical results do not prove a peer review advantage. Failures remain part of the evidence.

## 03:07 — Inspect what happened, not just what was said.

Open the hosted demo, choose a method and a condition, and inspect the result. The repository includes the transaction evidence, reproduction instructions, and an editable architecture diagram. Rehearsal is a synthetic proof of concept. The next step is testing whether it helps developers find real integration failures.
