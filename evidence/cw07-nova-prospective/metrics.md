# Practice batch metrics

Batch: `batch-b6f157f5ae11e54b0cf346a698c35a680a6834e94f9c2b0735b59b36d94e9352`
Scope: `live-model`

| Arm | Goal complete / planned | Recorded tokens | Complete usage cells | Tool calls (observed cells) | Recorded USD | Reserved USD | Median / p95 seconds (samples) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 15 / 20 | 0 | 20 / 20 | 601 (20) | 0.000000 | 0.000000 | 0.028 / 0.044 (20) |
| B1 | 11 / 20 | 1062906 | 20 / 20 | 313 (20) | 0.348051 | 0.000000 | 10.218 / 19.238 (20) |
| B2 | 8 / 20 | 3970008 | 20 / 20 | 886 (20) | 1.276936 | 0.000000 | 35.904 / 45.971 (20) |
| B3 | 7 / 20 | 2082674 | 20 / 20 | 602 (20) | 0.687024 | 0.000000 | 23.195 / 36.673 (20) |

Statuses retain the full denominator:

- B0: {"EVALUATED": 15, "EVALUATION_INCOMPLETE": 5}
- B1: {"EVALUATED": 11, "EVALUATION_INCOMPLETE": 9}
- B2: {"EVALUATED": 8, "EVALUATION_INCOMPLETE": 11, "REJECTED": 1}
- B3: {"EVALUATED": 7, "EVALUATION_INCOMPLETE": 13}

Entire uninterrupted cell, including learning and evaluation; excludes batch preparation and reporting. Not provider latency or recovery time.

Sum of recorded input, output, cache-read and cache-write tokens; partial usage remains partial. Missing and invalid evidence is unavailable.

Recorded costs exclude unresolved reservations; unexecuted cells are not free model runs. Offline fixture costs are fictional. These metrics do not establish model efficacy, held-out performance, provider billing, or developer time savings.
