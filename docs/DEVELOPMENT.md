# Development

The hosted preflight runs on AWS; [deployment instructions](../infra/serverless/README.md) are separate from the local observer and optional commerce backend.

## Setup

Prerequisites: Python 3.12+ for bootstrap, uv, Make and Git. The repository pins Python 3.12.13, Node 22.23.2 and locked dependencies. Docker with Compose v2 is needed only for Medusa.

```sh
make setup
make check
make check-browser
make dev
```

`make setup` downloads runtimes, dependencies and Chromium into ignored local directories. It preserves an existing `.env`. `make check` runs offline and fails if required dependencies are missing; it never constructs a paid model client. Use `scripts/dev/with-env.sh` for pinned tools.

The local UI is at `http://127.0.0.1:15173`, with an API on `127.0.0.1:18000`. Without an observer run it displays its unconfigured state. This is distinct from the hosted preflight. Ctrl+C stops the owned processes. Run browser tests and `make dev` sequentially because they share ports.

## Preview regression checks

```sh
scripts/dev/with-env.sh uv run --offline --no-sync pytest tests/preflight
make check-browser
```

Preview browser tests use explicit HTTP fixtures. The [verification summary](VERIFICATION.md) distinguishes those tests from the retained live AWS demonstration.

## Optional local commerce

In terminal A, run `make commerce`. In terminal B, run `make commerce-contract` for synthetic HTTP orders, or `make commerce-demo` for the SDK/Medusa walkthrough. These create local test data, not real payments. Stop the demo, then stop terminal A with Ctrl+C; volumes are preserved.

| Service | Loopback port |
|---|---:|
| Observer UI | 15173 |
| Observer API | 18000 |
| Operating gateway | 18001 |
| Medusa | 19000 |
| PostgreSQL | 55432 |
| Redis | 56379 |

Only the `rehearsal-dev` Compose project is owned by these commands. Existing processes, other projects, global runtimes and database volumes must be preserved.

## Model calls and generated files

`make agent-preflight` validates explicit model/rate/budget settings without calling AWS. `make agent-run` invokes a paid model and requires configured credentials and spending limits. Do not infer live model behavior from SDK fixtures.

Keep credentials in ignored `.env` and model/run outputs under `.local/`. Submission drafts and media belong in ignored `submissions/`. The historical raw experiment directory is not needed; the small required replay inputs live in `tests/fixtures/`. Future root `evidence/` outputs are ignored as a compatibility safeguard.

The [testing guide](TESTING.md) lists the hosted walkthrough. See [third-party notices](../THIRD_PARTY_NOTICES.md) for dependency licenses.
