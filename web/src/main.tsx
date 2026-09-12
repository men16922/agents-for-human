import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { useObserver } from './useObserver';
import { EvidencePanel, evidenceTitle, useEvidence } from './Evidence';
import { Commerce, stockLabel } from './Commerce';
import { MetricsPanel } from './MetricsPanel';
import { ExecutionPanel } from './Execution';
import './style.css';
import { CloudApp } from './CloudApp';
import { PreflightApp } from './PreflightApp';

const itemName = (name: string) => ({ tent: 'Tents', light: 'Lights' }[name] ?? name);
const number = (n: number | undefined) => n === undefined ? '—' : n.toLocaleString('en-US');
function App() {
  const { view: v, reconnect, metrics } = useObserver();
  const evidence = useEvidence(v.run);
  const [health, setHealth] = useState('Checking local API…');
  const [now, setNow] = useState(Date.now());
  const [latency, setLatency] = useState<number | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/health', { signal: controller.signal }).then(async r => {
      const h = await r.json();
      if (!r.ok || h.status !== 'ok' || h.phase !== 'development-foundation' || h.model_calls_enabled !== false) throw Error();
      setHealth('Local API connected');
    }).catch(() => { if (!controller.signal.aborted) setHealth('Cannot connect to the local API.'); });
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => { controller.abort(); clearInterval(timer); };
  }, []);
  useEffect(() => {
    if (v.observedAt === null) { setLatency(null); return; }
    // Two animation frames include a paint opportunity after the state commit.
    let second = 0;
    const first = requestAnimationFrame(() => { second = requestAnimationFrame(() => {
      if (metrics?.run === v.run) metrics.rendered(v.version);
      setLatency(Date.now() - v.observedAt! * 1000);
    }); });
    return () => { cancelAnimationFrame(first); cancelAnimationFrame(second); };
  }, [v.observedAt, v.version, v.run, metrics]);
  const s = v.snapshot, age = v.lastPoll === null ? null : (now / 1000 - v.lastPoll);
  const fresh = v.link === 'live' && !v.upstreamStale && age !== null && age >= 0 && age < 5;
  const linkLabel = v.link === 'unconfigured' ? 'No observation source' : v.link === 'invalid' ? 'Event validation failed' : v.link === 'connecting' ? 'Connecting' : fresh ? 'Live connection' : v.link === 'live' ? 'Observation delayed' : 'Disconnected';
  const entries = s ? Object.entries(s.goal.items) : [];
  const received = entries.reduce((n, [k, q]) => n + Math.min(s!.inventory[k] ?? 0, q), 0);
  const target = entries.reduce((n, [, q]) => n + q, 0);
  const receiptKnown = s?.commerce?.receipt_status !== 'UNAVAILABLE';
  const fulfilled = !!s && receiptKnown && entries.every(([k, q]) => (s.inventory[k] ?? 0) >= q);
  const suppliers = s?.suppliers ?? [];
  return <div className="app">
    <header className="topbar"><a className="brand" href="/" aria-label="Rehearsal home"><span className="brand-mark">r.</span>rehearsal<span className="brand-divider">/</span><span className="brand-section">Observatory</span></a><span className="local-tag">LOCAL POC · Read only</span></header>
    <main>
      <div className="page-heading"><div><span className="eyebrow">TRANSACTION OBSERVATORY</span><h1>See where every transaction stands.</h1><p>Follow deliveries and spending, from suppliers to the venue.</p></div><button onClick={reconnect} className="reconnect">↻ Reconnect</button></div>
      <div className="runbar"><span className={`connection ${fresh ? 'fresh' : 'stale'}`} data-testid="connection"><i />{linkLabel}</span><span className="run-id">{v.run ?? 'No run connected'}</span><span className="revision">v{v.version} · cursor <b data-testid="cursor">{v.cursor}</b></span></div>
      {!fresh && <div className="notice">{v.link === 'unconfigured' ? 'Connect a local run to see its observed state.' : v.link === 'invalid' ? 'The stream stopped because an event failed scope or content validation. Check the connection and retry.' : s ? 'Showing the last received state. It may no longer be current.' : 'Waiting for the first observation.'}</div>}
      <section className="workspace" aria-label="Run observation">
        <div className="map-panel panel"><div className="panel-heading"><div><span className="eyebrow">01 / WORLD</span><h2>Procurement map</h2></div><span className="tick" data-testid="tick">{s ? `${s.tick} / ${s.goal.deadline_tick} tick` : 'Clock unavailable'}</span></div>
          <div className="world-map">
            <svg viewBox={`0 0 760 ${Math.max(370, suppliers.length * 90 + 70)}`} role="img" aria-label="Observed suppliers, payment ledger and destination. Lines show system structure, not actual order routes.">
              <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#d9dfd7" /></pattern></defs>
              <rect width="760" height="100%" fill="url(#grid)" />
              {suppliers.map((name, i) => <g key={`${name}-${i}`}><path d={`M 208 ${85 + i * 90} H 270 V 175 H 310`} className="map-line" /><rect x="28" y={48 + i * 90} width="180" height="74" rx="10" className="supplier-node" /><text x="44" y={77 + i * 90} className="node-title">Supplier {name.length > 12 ? name.slice(0, 12) + '…' : name}</text><text x="44" y={100 + i * 90} className="node-note">{stockLabel(s, name)}</text></g>)}
              <path d="M 470 175 H 530" className="map-line" />
              <rect x="310" y="124" width="160" height="102" rx="12" className="ledger-node" /><text x="330" y="153" className="node-title">Payment ledger</text><text x="330" y="180" className="node-note">Spent {number(s?.balance.spent)}</text><text x="330" y="202" className="node-note">Reserved {number(s?.balance.reserved)}</text>
              <rect x="530" y="112" width="202" height="126" rx="12" className="venue-node" /><text x="550" y="142" className="venue-label">{s?.goal.recipient === 'venue' ? 'Event venue' : (s?.goal.recipient ?? 'Destination').slice(0, 12)}</text><text x="550" y="185" className="venue-quantity">{s && receiptKnown ? `${received} / ${target}` : '— / —'}</text><text x="550" y="214" className="venue-note">Observed items received</text>
              {!s && <text x="30" y="76" className="node-note">Supplier list unavailable</text>}
            </svg>
          </div><p className="map-scroll-hint">Scroll across the map to see the destination →</p><div className="map-caption"><span><i className="line-key" />System structure · not actual order routes</span><span>{s?.clock_mode ?? 'Clock mode unavailable'}</span></div>
        </div>
        <aside className="receipt-panel panel"><span className="eyebrow">02 / RECEIPT</span><h2>Delivery progress</h2><div className="receipt-total" data-testid="received">{s && receiptKnown ? received : '—'}<span> / {s ? target : '—'}</span></div><p className="receipt-state">{!s ? 'Receipt data unavailable' : !receiptKnown ? 'Receipt status unknown' : fulfilled ? 'Required quantities observed' : 'Awaiting delivery'}</p>
          <div className="items">{entries.map(([k, q]) => <div className="item" key={k}><div><span>{itemName(k)}</span><strong data-testid={`inventory-${k}`}>{receiptKnown ? number(s!.inventory[k] ?? 0) : '—'} <span>/ {q}</span></strong></div><progress aria-label={`${itemName(k)} received`} value={receiptKnown ? Math.min(s!.inventory[k] ?? 0, q) : 0} max={q} /></div>)}</div>
          <div className="verification"><span className="verification-icon">◇</span><div><strong>{evidenceTitle(evidence.data, s, v.run)}</strong><p>Observed receipts and the independent verdict are checked separately.</p></div></div>
        </aside>
      </section>
      <section className="balance-grid" aria-label="Synthetic budget ledger">{([['budget', 'Total budget'], ['spent', 'Spent'], ['reserved', 'Unresolved reservations'], ['available', 'Available budget']] as const).map(([key, label], i) => <div className={`balance-card ${key === 'available' ? 'available' : ''}`} key={key}><span className="balance-label"><span>0{i + 1}</span>{label}</span><strong data-testid={key}>{number(s?.balance[key])}<small>credits</small></strong></div>)}</section>
      <Commerce snapshot={s} />
      <section className="bottom-grid"><div className="panel events"><div className="panel-heading"><div><span className="eyebrow">03 / EVENT JOURNAL</span><h2>Event journal</h2></div><span className="muted">Last 30 · this connection</span></div>{!v.log.length ? <p className="empty">No events received yet.</p> : <ol>{v.log.map(e => <li key={e.key}><span className="event-dot" /><span>{e.label}</span><code>{e.detail}</code></li>)}</ol>}</div>
        <div className="panel freshness"><span className="eyebrow">04 / FRESHNESS</span><h2>Observation freshness</h2><dl><div><dt>Last customer poll</dt><dd>{age === null ? '—' : age < 0 ? 'Clock mismatch' : `${age.toFixed(1)}s ago`}</dd></div><div><dt>Observation → screen</dt><dd data-testid="latency">{latency === null ? '—' : latency < 0 ? 'Clock mismatch' : `${Math.round(latency).toLocaleString()} ms`}</dd></div><div><dt>Observation version</dt><dd>{v.version || '—'}</dd></div></dl><p>Local clock measurement for the latest rendered state. This does not measure latency from the external transaction or establish a performance target.</p></div></section>
      <MetricsPanel metrics={metrics} />
      <ExecutionPanel run={v.run} snapshot={s} />
      <EvidencePanel evidence={evidence} snapshot={s} run={v.run} fresh={fresh} />
      <footer><span role="status">{health}</span><span>Synthetic credits · no purchase controls · no model calls from this view</span></footer>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<StrictMode>{new URLSearchParams(location.search).has('preflight') || (import.meta.env.VITE_DEPLOYMENT === 'serverless' && !new URLSearchParams(location.search).has('legacy')) ? <PreflightApp /> : import.meta.env.VITE_DEPLOYMENT === 'serverless' ? <CloudApp /> : <App />}</StrictMode>);
