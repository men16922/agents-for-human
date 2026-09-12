import { useEffect, useState } from 'react';
import './preflight.css';

type Cell = { condition: string; status: string; spent: number; reserved: number; duplicate_payments: number; received_on_time: Record<string, number>; rejection: string | null; payment_recovery: string; artifact_sha256: string; run_id: string };
type Plan = { plan: { supplier: string; plan_sha256: string }; normal_spend: number | null; normal_arrival_minute: number | null; goals_met: number; planned_tests: number; eligible_for_handoff: boolean; cells: Cell[] };
type Brief = { decision: string; brief_sha256: string; expires_at?: number } & Record<string, unknown>;
export type Impact = { report_id: string; report_sha256: string; status: string; expires_at: number; proposed_supplier: string | null; recommended_supplier: string | null; coverage: { verified: number; planned: number }; snapshot: { captured_at: number; source_sha256: string; source: { revision: number; intent: { text: string } } }; plans: Plan[]; limitations: string[]; runtime_session_stopped: boolean };
type Run = { run_id: string; status: string; finalized: boolean; phase: string; usage: { model_calls: number; recorded_micro_usd: number }; report?: Impact; decision?: Brief | null };
const conditions = ['normal', 'stock-disappears', 'price-increases', 'payment-response-lost'];
const names: Record<string, string> = { normal: 'As quoted', 'stock-disappears': 'A loses tent stock', 'price-increases': 'A raises tent price', 'payment-response-lost': 'Payment reply lost' };
const usd = (n: number | null) => n === null ? '—' : `$${n}`;
const arrival = (n: number | null) => { if (n === null) return 'No delivery'; const total = 18 * 60 + n; const hour = Math.floor(total / 60) % 24; return `${['Wed', 'Thu', 'Fri', 'Sat', 'Sun', 'Mon', 'Tue'][Math.floor(total / 1440) % 7]}, ${hour % 12 || 12}:${String(total % 60).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'}`; };
const stamp = (n: number) => new Date(n * 1000).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' });
async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, body ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : { cache: 'no-store' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
function download(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function PreflightApp() {
  const [scenario, setScenario] = useState('family-camping');
  const [runId, setRunId] = useState(new URLSearchParams(location.search).get('preview') || '');
  const [run, setRun] = useState<Run | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now() / 1000);
  const [cell, setCell] = useState<{ supplier: string; value: Cell } | null>(null);
  const [brief, setBrief] = useState<Brief | null>(null);
  const report = run?.report;
  const expired = !!report && now >= report.expires_at;
  const active = !!runId && !run?.finalized;
  useEffect(() => { const t = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(t); }, []);
  useEffect(() => {
    if (!runId) return;
    let stopped = false; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await request<Run>(`/api/preflights/${encodeURIComponent(runId)}`);
        if (stopped) return;
        setRun(value); setBrief(value.decision || null); setError('');
        if (!value.finalized) timer = setTimeout(poll, 2500);
      } catch (e) { if (!stopped) { setError(String(e)); timer = setTimeout(poll, 5000); } }
    };
    void poll(); return () => { stopped = true; clearTimeout(timer); };
  }, [runId]);
  async function start() {
    setPending(true); setError('');
    try {
      const key = `preflight-pending-${scenario}`;
      const id = sessionStorage.getItem(key) || crypto.randomUUID(); sessionStorage.setItem(key, id);
      const created = await request<{ run_id: string }>('/api/preflights', { request_id: id, scenario });
      sessionStorage.removeItem(key); setRun(null); setBrief(null); setCell(null); setRunId(created.run_id);
      const url = new URL(location.href); url.searchParams.set('preview', created.run_id); history.replaceState({}, '', url);
    } catch (e) { setError(String(e)); } finally { setPending(false); }
  }
  async function decide(action: 'accept' | 'decline') {
    if (!report) return;
    setPending(true); setError('');
    try {
      const plan = report.plans.find(p => p.plan.supplier === report.recommended_supplier);
      const result = await request<Brief>(`/api/preflights/${runId}/decision`, { action, report_sha256: report.report_sha256, plan_sha256: plan?.plan.plan_sha256 || '' });
      setBrief(result);
    } catch (e) { setError(String(e)); } finally { setPending(false); }
  }
  async function evidence() {
    setPending(true); setError('');
    try { download(`${runId}-evidence.json`, await request(`/api/preflights/${runId}/evidence`)); }
    catch (e) { setError(String(e)); } finally { setPending(false); }
  }
  return <div className="preflight">
    <header className="pf-nav"><a href="/" className="pf-brand"><b>r.</b> rehearsal <span>/ Before you act</span></a><span className="pf-live"><i /> AWS · Nova 2 Lite</span></header>
    <main>
      <section className="pf-hero"><div><span className="pf-eyebrow">AGENT TRANSACTION PREFLIGHT</span><h1>See the impact.<br /><em>Then decide.</em></h1><p>A shopping agent can place an order in seconds.<br />First, find out what its plan could cost you.</p><div className="pf-flow"><span>01 Request</span><b>→</b><span>02 Rehearse</span><b>→</b><span>03 Evidence</span><b>→</b><span>04 Your decision</span></div></div><div className="pf-boundary"><span className="pf-eyebrow">EXECUTION BOUNDARY</span><strong>0</strong><h2>External orders placed</h2><p>Plans run in isolated virtual worlds. The flow stops at an impact report.</p><span className="pf-chip">Synthetic catalog · no Amazon connection</span></div></section>
      <section className="pf-request" aria-labelledby="request-title"><div className="pf-request-icon" aria-hidden="true">⌁</div><div><span className="pf-eyebrow">THE REQUEST / FAMILY CAMPING</span><h2 id="request-title">“We leave on Saturday. Can you get us ready?”</h2><p>One tent. Two lanterns. At home by <b>Friday, 6 PM</b>.<br />Keep the complete basket under <b>$200, including shipping</b>. No lanterns without a tent.</p></div><div className="pf-actions"><label htmlFor="pf-case">Catalog condition</label><select id="pf-case" value={scenario} disabled={active || pending} onChange={e => setScenario(e.target.value)}><option value="family-camping">Camping essentials available</option><option value="no-tents">All tents unavailable</option></select><button className="pf-primary" onClick={start} disabled={active || pending}>{pending && !report ? 'Starting…' : active ? 'Rehearsal in progress…' : report ? 'Run a new rehearsal ↗' : 'Rehearse this request ↗'}</button><small>Generates a new report · bounded paid model run</small></div></section>
      {error && <div className="pf-error" role="alert">{error.replace('Error: ', '')}. {active ? 'Reconnecting to this run.' : 'Retrying a failed start reuses its request ID.'}</div>}
      {active && <section className="pf-progress" role="status"><span className="pf-spinner" /><div><h2>{run?.phase === 'FINISHED' ? 'Independently checking the evidence' : run?.phase === 'PLANNING_AND_SIMULATING' ? 'Nova is planning and rehearsing' : 'Starting an isolated preview session'}</h2><p>{run?.usage.model_calls || 0} model calls recorded · The source catalog is read only. No external purchases.</p><code>{runId}</code></div></section>}
      {!runId && <section className="pf-preview"><div><span>WHAT THE REPORT WILL ANSWER</span><h2>The cheapest basket<br />may miss the trip.</h2></div><p>Compare three suppliers under four explicit conditions: the quoted offer, stock disappearing, a price increase, and a missing payment reply. See delivery, spending and unresolved payments for every run.</p></section>}
      {report && <>
        <section className="pf-report-head" aria-labelledby="report-title"><div><span className="pf-eyebrow">IMPACT REPORT / {report.coverage.verified} OF {report.coverage.planned} RUNS VERIFIED</span><h2 id="report-title">{report.recommended_supplier ? `Supplier ${report.recommended_supplier} meets the tested conditions.` : 'Do not proceed with these plans.'}</h2><p>{report.recommended_supplier ? `The report compares spending and delivery across all tested conditions. Nova initially proposed supplier ${report.proposed_supplier || '—'}.` : 'No plan has complete evidence of meeting every tested condition. Review the results before trying again.'}</p></div><span className={`pf-status ${report.status === 'REPORT_READY' ? '' : 'bad'}`}>{report.status === 'REPORT_READY' ? 'Evidence checked' : 'Review required'}</span></section>
        <section className="pf-plan-grid" aria-label="Plan comparison">{report.plans.map(p => <article key={p.plan.supplier} className={`pf-plan ${p.eligible_for_handoff ? 'recommended' : ''}`}><div className="pf-plan-top"><span>SUPPLIER {p.plan.supplier}</span><span>{p.eligible_for_handoff ? 'Recommended for review' : p.plan.supplier === report.proposed_supplier ? 'Agent’s initial proposal' : 'Alternative'}</span></div><strong>{usd(p.normal_spend)}<small>including shipping</small></strong><p className="pf-arrival">{arrival(p.normal_arrival_minute)}</p><div className="pf-score"><b>{p.goals_met} / {p.planned_tests}</b><span>tested conditions met</span></div><p>{p.normal_arrival_minute === null ? 'No complete basket delivered in the normal condition.' : p.plan.supplier === 'A' ? 'Lower price; exposed to the tested stock and price changes.' : p.plan.supplier === 'B' ? 'Within the budget and deadline in this test set.' : 'Lower price; simulated delivery misses Friday’s deadline.'}</p></article>)}</section>
        <section className="pf-matrix" aria-labelledby="matrix-title"><div className="pf-section-top"><div><span className="pf-eyebrow">12 ISOLATED RUNS / SAME SOURCE SNAPSHOT</span><h2 id="matrix-title">What changes when things go wrong?</h2></div><p>Click any result to inspect its evidence.</p></div><div className="pf-table-scroll"><table><thead><tr><th scope="col">Test condition</th>{report.plans.map(p => <th scope="col" key={p.plan.supplier}>Supplier {p.plan.supplier}</th>)}</tr></thead><tbody>{conditions.map(condition => <tr key={condition}><th scope="row">{names[condition]}</th>{report.plans.map(p => { const c = p.cells.find(c => c.condition === condition); return <td key={p.plan.supplier}>{c ? <button className={`pf-cell ${c.status === 'COMPLETE' ? 'pass' : 'fail'}`} aria-label={`${p.plan.supplier}: ${names[condition]}`} onClick={() => setCell({ supplier: p.plan.supplier, value: c })}><b>{c.status === 'COMPLETE' ? 'Goal met' : c.rejection ? 'Blocked' : 'Missed deadline'}</b><span>{usd(c.spent)} spent · {c.reserved} unresolved ↗</span></button> : <span>Not verified</span>}</td>; })}</tr>)}</tbody></table></div><p className="pf-scope">Coverage: stock and price shocks target A. Disruptions at B are not tested. These counts are evidence for this test set, not real-world success probabilities.</p></section>
        {cell && <section className="pf-detail" aria-label="Selected simulation evidence"><button className="pf-close" onClick={() => setCell(null)} aria-label="Close simulation detail">×</button><span className="pf-eyebrow">SUPPLIER {cell.supplier} / {names[cell.value.condition]}</span><h2>{cell.value.rejection || (cell.value.status === 'COMPLETE' ? 'The whole basket arrived before the deadline.' : 'The basket arrived too late.')}</h2><div className="pf-detail-stats"><span><b>{usd(cell.value.spent)}</b>Simulated spending</span><span><b>{cell.value.reserved}</b>Unresolved reservation</span><span><b>{cell.value.duplicate_payments}</b>Duplicate payments</span></div>{cell.value.payment_recovery === 'RECONCILED_SAME_ORDER' && <p>A payment committed, but its reply was hidden. The simulation kept the reservation, queried that same order and reconciled its status. It did not create a second payment.</p>}<p>Received on time: {cell.value.received_on_time.tent || 0} tent · {cell.value.received_on_time.light || 0} lanterns.</p><code>Artifact SHA-256: {cell.value.artifact_sha256}</code></section>}
        <section className="pf-decision" aria-labelledby="decision-title"><div><span className="pf-eyebrow">YOUR DECISION / NO AUTOMATIC CHECKOUT</span><h2 id="decision-title">{brief?.decision === 'DECLINED' ? 'Plan declined. Nothing was ordered.' : brief ? 'Execution brief recorded.' : expired ? 'This report has expired.' : 'Enough evidence to take the next step?'}</h2><p>{brief ? 'This records a decision about simulation evidence. It is not an order, a payment authorization or a guarantee. The brief retains its original expiry.' : expired ? 'Run a new rehearsal to capture current source conditions before exporting an execution brief.' : 'Accepting rechecks the source revision and report expiry, then records a brief bound to this exact plan. No external order is placed.'}</p></div><div className="pf-decision-buttons">{brief ? <button className="pf-primary" onClick={() => download(`${runId}-decision.json`, brief)}>Download decision brief ↓</button> : <><button className="pf-primary" disabled={pending || expired || !report.recommended_supplier || report.status !== 'REPORT_READY'} onClick={() => decide('accept')}>Accept plan {report.recommended_supplier || '—'} &amp; export brief</button><button className="pf-secondary" disabled={pending} onClick={() => decide('decline')}>Decline these plans</button></>}</div></section>
        <section className="pf-evidence"><div><h2>Evidence you can inspect.</h2><p>Captured {stamp(report.snapshot.captured_at)} · revision {report.snapshot.source.revision}<br />Report expires {stamp(report.expires_at)} {expired ? '· Expired' : ''}<br />Nova usage: {run!.usage.model_calls} calls · ${(run!.usage.recorded_micro_usd / 1e6).toFixed(6)} recorded</p><code>Source {report.snapshot.source_sha256}</code><code>Report {report.report_sha256}</code><p>{report.runtime_session_stopped ? 'Preview runtime stopped after evidence export.' : 'Runtime termination has not been confirmed.'}</p><button className="pf-secondary" disabled={pending} onClick={evidence}>Download report, journals &amp; tool trace ↓</button></div><details><summary>What this evidence does—and does not—show</summary><ul>{report.limitations.map(l => <li key={l}>{l}</li>)}</ul></details></section>
      </>}
      <footer><span>REHEARSAL · Test the plan before it touches a transaction.</span><a href="/architecture/rehearsal-serverless.drawio">AWS architecture ↗</a></footer>
    </main>
  </div>;
}
