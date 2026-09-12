# Regression fixtures

These small, fixed inputs are required by the existing commerce, observer and execution tests. They were extracted byte-for-byte from the previously published `6967eba` synthetic Medusa/SDK captures. They contain no real transactions or model-efficacy claims.

The original root `evidence/` directory, videos and experiment logs are not required. Keep fixtures separate from generated outputs; tests copy them into temporary directories before mutation. The notification batch includes its small SQLite accounting fixture so missing/held reservations remain testable.
