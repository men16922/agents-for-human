# Architecture

The hosted application prepares evidence before a transaction. It does not connect to Amazon or authorize real payments.

![AWS architecture](assets/architecture.png)

[Editable draw.io](assets/architecture.drawio) · [SVG](assets/architecture.svg) · [Deployment](../infra/serverless/README.md)

## Preview flow

1. CloudFront serves the React application from private S3 and routes API requests to API Gateway.
2. Lambda captures the server-owned request/catalog snapshot and reserves a bounded model allowance in DynamoDB.
3. Step Functions starts a dedicated AgentCore preview. Nova 2 Lite uses Strands tools to inspect, propose and rehearse a fixed purchase plan.
4. Twelve application-isolated worlds execute in temporary runtime memory. Each exports its state and journal to S3; no database is provisioned per cell.
5. A separate Lambda stops the runtime, independently verifies all planned cells and writes the final report.
6. The person declines or accepts a qualifying plan for execution review. The decision transaction rechecks source revision and report/plan identity. The brief expires fifteen minutes after snapshot capture; replay does not extend validity.

## Authority and state

| Component | Owns | Boundary |
|---|---|---|
| API/control plane | Frozen source, admission and decisions | Server-owned intent; one finite shared allowance |
| Preview agent | Initial proposal and simulation tools | No commerce/seller invocation or commerce-table write permission |
| Simulator | Per-cell state transitions and journals | Fresh state per condition; no external orders |
| Finalizer/verifier | Final audited report | Writes outside model-writable prefixes; incomplete evidence blocks handoff |
| Browser | Comparison, detail and explicit decision | No model or AWS credentials; a public demo click is not authenticated financial approval |

DynamoDB persists source revisions, admission, run state and decisions. S3 preserves exported artifacts after runtime shutdown. Reopening a report does not invoke Nova. Storage, logs and service requests remain metered.

The earlier synthetic commerce workflow remains available at `?legacy=1`. It uses separate DynamoDB commerce state and an independent seller. The optional local Medusa/PostgreSQL/Redis stack is not part of the hosted deployment.

Implementation: [preflight](../src/rehearsal/preflight/) · [serverless](../src/rehearsal/serverless/). Verification scope is summarized in [VERIFICATION.md](VERIFICATION.md).
