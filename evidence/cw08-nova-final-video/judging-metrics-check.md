# Practice batch metrics

Batch: `batch-4735f81fd9d7d05d0180a3b42323abca78107b1a35cd605c1df774ff9fef6d5d`
Scope: `live-model`

| Arm | Goal complete / planned | Recorded tokens | Complete usage cells | Tool calls (observed cells) | Recorded USD | Reserved USD | Median / p95 seconds (samples) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 4 / 5 | 0 | 5 / 5 | 129 (5) | 0.000000 | 0.000000 | 0.024 / 0.042 (5) |
| B1 | 3 / 5 | 281719 | 5 / 5 | 80 (5) | 0.092444 | 0.000000 | 10.451 / 27.908 (5) |
| B2 | 3 / 5 | 870045 | 5 / 5 | 203 (5) | 0.280186 | 0.000000 | 35.050 / 38.012 (5) |
| B3 | 4 / 5 | 432936 | 5 / 5 | 126 (5) | 0.142691 | 0.000000 | 22.387 / 26.559 (5) |

Statuses retain the full denominator:

- B0: {"EVALUATED": 4, "EVALUATION_INCOMPLETE": 1}
- B1: {"EVALUATED": 3, "EVALUATION_INCOMPLETE": 2}
- B2: {"EVALUATED": 3, "EVALUATION_INCOMPLETE": 2}
- B3: {"EVALUATED": 4, "EVALUATION_INCOMPLETE": 1}

Entire uninterrupted cell, including learning and evaluation; excludes batch preparation and reporting. Not provider latency or recovery time.

Sum of recorded input, output, cache-read and cache-write tokens; partial usage remains partial. Missing and invalid evidence is unavailable.

Recorded costs exclude unresolved reservations; unexecuted cells are not free model runs. Offline fixture costs are fictional. These metrics do not establish model efficacy, held-out performance, provider billing, or developer time savings.

