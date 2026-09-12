# Third-party materials

The root MIT license covers this project's original source. Dependencies retain their own licenses. Do not redistribute `.tooling/`, `node_modules/`, `.venv/`, `.env`, local logs or database volumes as project source.

- Strands Agents, React, Vite, FastAPI and Medusa core are installed dependencies; exact versions and integrity hashes are in `uv.lock` and `package-lock.json`.
- Medusa 2.20.1 includes separately licensed Enterprise materials, including RBAC. This POC does not enable Enterprise features (`MEDUSA_FF_RBAC=false`). The root MIT license does not relicense those packages. Review the installed package notices and the release packaging before publication.
- PostgreSQL and Redis 7.2 are independent local development services pinned by image digest. Their upstream notices apply to the images.

Sources: [Medusa license](https://github.com/medusajs/medusa/blob/v2.20.1/LICENSE), [Medusa RBAC license](https://github.com/medusajs/medusa/blob/v2.20.1/packages/modules/rbac/LICENSE).

- AWS architecture icons embedded in `docs/assets/architecture.*` are unmodified assets from the official 2026-07-31 [AWS Architecture Icons package](https://aws.amazon.com/architecture/icons/). They are embedded in the editable draw.io and SVG diagrams. AWS owns these service icons and trademarks; the project MIT license does not relicense them. Exact source paths are recorded in [icon provenance](docs/assets/aws-sources.json).
