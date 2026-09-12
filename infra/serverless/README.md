# AWS serverless deployment

The deployed English demo is at **https://d1u9yhii3gor6j.cloudfront.net**. Its current deployment uses account `908601828278`, region `us-west-2`, and the `q-user` profile for operator commands. Model inference uses the global Amazon Nova 2 Lite profile. Account credentials are never included in the browser or deployment package.

The CloudFormation stacks are `rehearsal-serverless-base` (retained DynamoDB/S3 data) and `rehearsal-serverless-app` (API, Lambda, Step Functions, AgentCore and CloudFront). [Editable draw.io](../../docs/assets/architecture.drawio) · [SVG preview](../../docs/assets/architecture.svg) · [actual AWS evidence](../../docs/VERIFICATION.md).

## Reproduce a deployment

Run the ordinary local setup and checks first. Dependency installation and the final deployment command use the network. The deployment changes AWS resources and may incur charges; it does not invoke a model automatically.

```sh
mkdir -p .local/serverless-deploy
scripts/dev/with-env.sh uv export --frozen --no-dev --no-emit-project \
  --output-file .local/serverless-deploy/requirements.txt
scripts/dev/with-env.sh uv pip install --python-platform aarch64-manylinux2014 \
  --python-version 3.12 --only-binary=:all: \
  --target .local/serverless-deploy/agent-package \
  -r .local/serverless-deploy/requirements.txt
scripts/dev/with-env.sh uv run --offline --no-sync python scripts/dev/deploy_serverless.py \
  --execute --profile q-user --region us-west-2
```

The deployment script builds a source-only package plus pinned ARM64 dependencies, uploads the versioned code ZIP, applies the reviewed templates, builds the cloud UI and publishes it to the private site bucket. The generated package contains no `.env`, credentials, local evidence, Medusa dependencies or sibling project. CloudFront serves `/api/*` without caching and uses origin access control for static objects. `make check` still builds the local observer; the deployed UI uses `VITE_DEPLOYMENT=serverless` and a separate `web/dist-cloud` output.

On a newly created control table only, an explicitly requested `--initialize-budget` adds the reviewed initial $4 model allowance, 40 admissions and October 10, 2026 UTC closing time. Conditional insertion preserves an existing budget, even when that flag is repeated. Redeployment never refills or increases the budget. The script deliberately targets the reviewed account and region; adapt and review the guard before deploying elsewhere.

## Preflight preview and decision

The default UI uses `/api/preflights`. It accepts only a request ID and one of two fixed catalog cases. Deployment conditionally seeds source records and preserves existing revisions. The API writes an immutable input snapshot, reserves the existing shared budget and starts `rehearsal-serverless-preflight`.

The separate preview AgentCore role has no commerce Lambda invocation or commerce-table write access. It reads the input, calls Nova and executes twelve virtual worlds in memory. S3 preserves raw evidence and usage; a separate finalizer stops the runtime, audits the journals and writes the report outside model-writable prefixes.

An acceptance binds the selected plan hash and final report hash. A fifteen-minute expiry and source recheck guard the handoff; source validation and the decision write share one DynamoDB transaction. Repeated decisions return the original brief, including its original expiry. The export is evidence for execution review, not a production payment authorization.

`?legacy=1` retains the earlier experiment UI and the separate workflow below. Do not confuse its synthetic commerce-table purchases with the preview, which creates no commerce-table rows. [Actual preview audit](../../docs/VERIFICATION.md).

## Legacy experiment execution and shutdown

The public API accepts only `request_id`, `method` and a named `scenario`. A DynamoDB transaction reserves one execution slot and its model allowance. Step Functions bootstraps the synthetic commerce state, invokes AgentCore and advances an independent seller every two seconds. Learning finishes before the live purchase clock starts. Each experiment has its own DynamoDB partition; it does not create a physical table or a persistent database server.

B2 and B3 retain the existing isolated SQLite practice worlds inside the temporary AgentCore session. Those files and the shared usage ledger are exported to S3. Production commerce state and its journal are in DynamoDB. The deployed path does not run Medusa, PostgreSQL or Redis; their local implementation and historical evidence remain available.

The finalizer atomically closes admission for commerce writes, calls `StopRuntimeSession`, independently replays the journal, saves the evidence, and reconciles the global reservation. The stopped sessions in the deployment audit returned `ResourceNotFoundException` on a separate check. Missing provider usage retains its full cost reservation. A missing commerce genesis becomes an invalid result, not a successful transaction. Claiming an already closing run is rejected.

Runtime idle timeout is 60 seconds and maximum lifetime is 420 seconds. The Standard workflow is also bounded. There is no EC2, ECS/Fargate service, RDS, Redis, load balancer, NAT gateway or provisioned concurrency in these stacks. Lambda and Runtime work is metered when executed; S3/DynamoDB storage, requests, logs and other service usage still incur charges. This is not a promise of a zero AWS bill. The application ledger estimates model costs from provider usage; it does not reconcile infrastructure charges or the final invoice.

To stop admitting new demo runs, an operator can set the existing `GLOBAL/BUDGET` row's `closes_at` to the present epoch. Preserve `remaining`, reservations and existing runs. Allow an active workflow to finalize. Do not delete data to stop compute. To remove the public deployment later, delete only the app stack after confirming no active workflow; base buckets/tables use retention policies to preserve evidence. These are maintenance instructions, not actions performed automatically.

## Official references

- [AgentCore Python code ZIP deployment](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-code-deploy-python.html)
- [Stop an AgentCore session](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-stop-session.html)
- [DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)
- [Step Functions Wait state](https://docs.aws.amazon.com/step-functions/latest/dg/state-wait.html)
