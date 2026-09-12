# Rehearsal — final preflight video script

2:53, 1080p, actual visible Chrome, Daniel English narration, 28 captions. [Video](../../submissions/video/rehearsal-demo.mp4) · [Audit](../test/preflight-impact.md). Screens use the actual deployed preview; pauses are labelled.

## 0:00 — See the impact. Then decide.

Before a shopping agent spends your money, what would its plan actually do? Rehearsal measures the impact first.

## 0:09 — A real request. A decision worth rehearsing.

We leave for our first family camping trip on Saturday. One tent, two lanterns, at home by Friday evening. Two hundred dollars, including shipping. Let’s rehearse before ordering.

## 0:25 — Nova proposes. Isolated worlds measure.

This is the deployed dashboard in Google Chrome. Amazon Nova 2 Lite proposes a plan. Three supplier plans are tested in twelve isolated runs. No external order or payment is created.

## 0:43 — The initial plan is cheaper. The evidence changes the choice.

Nova initially proposed supplier A: one hundred forty-nine dollars. But A meets only two of the four tested conditions. B costs thirty dollars more and meets all four. The cheapest option, C, arrives after the trip.

## 1:02 — Compare every tested outcome.

The report keeps every result visible. If A loses stock or raises its price, its purchase is blocked. The matrix shows spending and unresolved reservations. These counts describe this test set, not real-world success probabilities.

## 1:22 — A missing payment reply does not mean a failed payment.

Here, a simulated payment commits and its reply is hidden. Rehearsal retains the reservation and queries the same order. It confirms the payment without creating another one. The verified result is one complete basket and zero duplicate payments.

## 1:45 — The report stops. The person decides.

Now I accept plan B for review. The server rechecks the source and report expiry, then records a brief bound to this exact plan. I can download it. This is execution evidence, not a purchase or payment authorization.

## 2:05 — Evidence survives the session.

Reloading restores the decision. The evidence includes source and report hashes, raw journals and model usage. The limits remain visible: a synthetic catalog, simulated delivery, and stock and price shocks aimed only at A.

## 2:23 — On-demand compute. Durable evidence.

AgentCore and Nova run on demand. A separate Lambda verifies the evidence and stops the preview session. Its IAM role cannot invoke commerce tools. Storage and service requests remain metered.

## 2:42 — The consequence before the commitment.

Rehearsal turns an agent’s plan into inspectable evidence, before it affects a real transaction. Plan. Measure. Decide.
