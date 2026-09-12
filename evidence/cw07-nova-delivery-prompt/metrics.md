# Practice batch metrics

Batch: `batch-dd03e342c1793ce3df3295ee07f24d54b1aa5b281b8d4dba2b547bf90b7afeab`
Scope: `live-model`

| Arm | Goal complete / planned | Recorded tokens | Complete usage cells | Tool calls (observed cells) | Recorded USD | Reserved USD | Median / p95 seconds (samples) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 4 / 5 | 0 | 5 / 5 | 129 (5) | 0.000000 | 0.000000 | 0.024 / 0.042 (5) |
| B1 | 4 / 5 | 208079 | 5 / 5 | 64 (5) | 0.068533 | 0.000000 | 9.587 / 13.402 (5) |
| B2 | 3 / 5 | 877153 | 5 / 5 | 192 (5) | 0.281501 | 0.000000 | 29.623 / 45.111 (5) |
| B3 | 4 / 5 | 413867 | 5 / 5 | 119 (5) | 0.136343 | 0.000000 | 19.325 / 22.676 (5) |

Statuses retain the full denominator:

- B0: {"EVALUATED": 4, "EVALUATION_INCOMPLETE": 1}
- B1: {"EVALUATED": 4, "EVALUATION_INCOMPLETE": 1}
- B2: {"EVALUATED": 3, "EVALUATION_INCOMPLETE": 1, "REJECTED": 1}
- B3: {"EVALUATED": 4, "EVALUATION_INCOMPLETE": 1}

Entire uninterrupted cell, including learning and evaluation; excludes batch preparation and reporting. Not provider latency or recovery time.

Sum of recorded input, output, cache-read and cache-write tokens; partial usage remains partial. Missing and invalid evidence is unavailable.

Recorded costs exclude unresolved reservations; unexecuted cells are not free model runs. Offline fixture costs are fictional. These metrics do not establish model efficacy, held-out performance, provider billing, or developer time savings.
