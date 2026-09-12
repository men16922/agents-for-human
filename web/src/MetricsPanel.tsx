import { useState } from 'react';
import type { ObservationMetrics } from './metrics';
const names: Record<string, string> = { poll: 'Server poll', publication: 'Observation → publication', transport: 'Publication → receipt', render: 'Receipt → render', observed_to_render: 'Observation → render', poll_to_render: 'Poll start → render' };
const display = (n: number | null) => n === null ? '—' : Math.round(n).toLocaleString('en-US');
export function MetricsPanel({ metrics }: { metrics: ObservationMetrics | null }) {
  const [type, setType] = useState('all');
  const summary = metrics?.summary(type === 'all' ? undefined : metrics.rows.filter(r => r.event_type === type));
  const download = () => {
    if (!metrics) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(metrics.export(), null, 2) + '\n'], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = `latency-${metrics.run}.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section className="panel metric-panel" aria-label="Observation latency samples"><div className="panel-heading"><div><span className="eyebrow">LATENCY SAMPLES</span><h2>Observation latency samples</h2></div><button className="reconnect" disabled={!metrics?.rows.length} onClick={download}>Download metrics JSON</button></div>
    <p className="commerce-caption">Up to 2,000 samples from this browser connection · milliseconds (ms) · not latency from the external transaction.</p>
    <label className="metric-filter">Sample type <select aria-label="Sample type" value={type} onChange={e => setType(e.target.value)}><option value="all">All events</option><option value="delivery.observed">Delivery observed</option><option value="state.observed">State change</option><option value="clock.observed">Clock update</option><option value="snapshot.observed">Initial observation</option></select></label>
    <div className="table-scroll"><table data-testid="metrics-table"><thead><tr><th>Stage</th><th>Valid n</th><th>p50</th><th>p95</th><th>Max</th><th>Excluded n</th></tr></thead><tbody>{Object.entries(names).map(([key, name]) => { const d = summary?.[key]; return <tr key={key}><td>{name}</td><td data-testid={`metric-n-${key}`}>{d?.n ?? 0}</td><td>{display(d?.p50 ?? null)}</td><td>{display(d?.p95 ?? null)}</td><td>{display(d?.max ?? null)}</td><td>{d ? Object.values(d.excluded).reduce((a, b) => a + b, 0) : 0}</td></tr>; })}</tbody></table></div>
    <p className="metric-counts">Received events {metrics ? metrics.counters.observation + metrics.counters.snapshot : 0} · Duplicates {metrics?.counters.duplicate ?? 0} · Older versions {metrics?.counters.old ?? 0} · Stream connection attempts {metrics?.counters.connection_attempts ?? 0} · Evicted {metrics?.counters.evicted ?? 0}</p>
    <p className="evidence-scope">Polls count unique events; publication and receipt count deliveries including duplicates; rendering counts displayed states. Missing timestamps, clock reversal, hidden tabs and batching exclusions are retained in JSON. Small samples do not establish a performance target.</p>
  </section>;
}
