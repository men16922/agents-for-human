# Rehearsal — Chrome walkthrough transcript

English narration: ElevenLabs Daniel. New, visible Google Chrome recording of the deployed AWS demo. All transactions are synthetic.

## 00:00 — Can an agent still deliver?

Can an AI purchasing agent still deliver when stock disappears? Let's run that experiment in Rehearsal.

## 00:09 — Choose the experiment. Then press Run.

The goal is three tents and six lights, within five hundred synthetic credits. Four methods range from fixed rules to practice and peer review. I'll choose peer review, select stock disappears, and start.

## 00:29 — Practice before the live clock.

First, the agent practices in an isolated world. An independent reviewer checks its policy without purchasing tools. The live purchase clock has not started yet.

## 00:45 — Stock disappears. Nova buys from supplier B.

Now the live world starts. Supplier A loses its tents. Nova chooses supplier B and authorizes three hundred and eighty credits. Watch the received count: payment alone is not delivery. The seller advances independently, and the verifier waits for the transaction evidence.

## 01:15 — 9 items received. Independently verified.

All nine items arrived. The independent audit confirms the goal, with three hundred and eighty credits spent and nothing reserved. Practice, review, and purchasing used twenty-three model calls, costing about two point three cents.

## 01:32 — Read the events behind the verdict.

The timeline separates authorization, capture, and delivery. The review kept the existing policy in this run. A successful demonstration does not prove that peer review improves results.

## 01:48 — Refresh. The same experiment is still here.

Refreshing retrieves the same experiment and its verified result. The runtime session has been stopped, while the transaction evidence remains available.

## 02:00 — Built on AWS serverless services.

Nova runs through Strands on AgentCore. Lambda and DynamoDB own the commerce records. Step Functions runs the seller and final audit, and S3 preserves the evidence after the session stops.

## 02:16 — Rehearse the transaction. Inspect the evidence.

Try the live demo. Choose a condition, watch the purchase, and inspect what actually arrived. Source, evidence, and the editable AWS architecture are included.
