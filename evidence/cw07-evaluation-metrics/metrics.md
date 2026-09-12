# Practice batch metrics

Batch: `batch-2141506c63e94da7ed9209f0ee98eec7c673d8d3f0594781fc3815856b50c14a`
Scope: `offline-scripted-model`

| Arm | Goal complete / planned | Recorded tokens | Complete usage cells | Tool calls (observed cells) | Recorded USD | Reserved USD | Median / p95 seconds (samples) |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 20 / 20 | 0 | 20 / 20 | 520 (20) | 0.000000 | 0.000000 | 0.031 / 0.039 (20) |
| B1 | 20 / 20 | 5800 | 20 / 20 | 270 (20) | 0.008120 | 0.000000 | 0.062 / 0.071 (20) |
| B2 | 20 / 20 | 15000 | 20 / 20 | 710 (20) | 0.021000 | 0.000000 | 0.171 / 0.184 (20) |
| B3 | 20 / 20 | 14600 | 20 / 20 | 630 (20) | 0.020440 | 0.000000 | 0.163 / 0.198 (20) |

Statuses retain the full denominator:

- B0: {"EVALUATED": 20}
- B1: {"EVALUATED": 20}
- B2: {"EVALUATED": 20}
- B3: {"EVALUATED": 20}

Entire uninterrupted cell, including learning and evaluation; excludes batch preparation and reporting. Not provider latency or recovery time.

Sum of recorded input, output, cache-read and cache-write tokens; partial usage remains partial. Missing and invalid evidence is unavailable.

Recorded costs exclude unresolved reservations; unexecuted cells are not free model runs. Offline fixture costs are fictional. These metrics do not establish model efficacy, held-out performance, provider billing, or developer time savings.

