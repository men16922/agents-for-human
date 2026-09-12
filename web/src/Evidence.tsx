import { useEffect, useState } from 'react';
import { integer, type Snapshot } from './observation';

type Artifact = { run_id: string; goal: Snapshot['goal']; budget: number; sha256: string; bytes: number; captured_at_tick: number };
type Verdict = { status: 'COMPLETE' | 'INCOMPLETE' | 'FAILED' | 'UNKNOWN'; errors: string[]; spent?: number; reserved?: number; received_on_time?: Record<string, number> };
export type Evidence = { status: 'UNCONFIGURED' | 'PENDING' | 'REJECTED' | 'VERIFIED'; reason: string | null; run_id: string | null;
  artifact: Artifact | null; verdict: Verdict | null; checked_at: number; historical: true; verifier?: { name: string; sha256: string } };
const same = (a: Record<string, number>, b: Record<string, number>) => Object.keys(a).length === Object.keys(b).length && Object.entries(a).every(([k, v]) => b[k] === v);
const sameGoal = (a: Snapshot['goal'], b: Snapshot['goal']) => a.recipient === b.recipient && a.deadline_tick === b.deadline_tick && same(a.items, b.items);
const labels: Record<string, string> = { COMPLETE: 'Goal complete at evidence capture', INCOMPLETE: 'Incomplete at evidence capture', FAILED: 'Independent verification failed', UNKNOWN: 'Insufficient evidence · verdict unknown' };
const reasons: Record<string, string> = { EVIDENCE_NOT_CONFIGURED: 'No independent evidence selected.', EVIDENCE_NOT_READY: 'Waiting for the selected evidence file.', EVIDENCE_HASH_MISMATCH: 'The original file does not match the selected hash.', EVIDENCE_RUN_MISMATCH: 'The observed run and evidence run differ.', INVALID_EVIDENCE_SELECTION: 'Cannot validate the evidence selection.', INVALID_EVIDENCE: 'Cannot read or verify the original evidence.' };
function parse(value: Evidence): Evidence {
  if (!value || !['UNCONFIGURED', 'PENDING', 'REJECTED', 'VERIFIED'].includes(value.status) || value.historical !== true || !Number.isFinite(value.checked_at)) throw Error();
  if (value.status === 'VERIFIED') {
    const a = value.artifact, v = value.verdict;
    if (!a || !v || !Object.hasOwn(labels, v.status) || !/^[a-f0-9]{64}$/.test(a.sha256) || a.run_id !== value.run_id || !Array.isArray(v.errors) || !v.errors.every(e => typeof e === 'string') || !a.goal?.items || !value.verifier || !/^[a-f0-9]{64}$/.test(value.verifier.sha256)) throw Error();
    integer(a.budget, 1); integer(a.captured_at_tick); integer(a.bytes, 1); integer(a.goal.deadline_tick, 1);
    for (const q of Object.values(a.goal.items)) integer(q, 1);
    if (v.status === 'COMPLETE' || v.spent !== undefined) {
      integer(v.spent); integer(v.reserved);
      if (!v.received_on_time) throw Error();
      for (const q of Object.values(v.received_on_time)) integer(q);
    }
  }
  return value;
}
export function useEvidence(run: string | null) {
  const [data, setData] = useState<Evidence | null>(null), [error, setError] = useState(false), [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setData(null); setError(false);
    fetch('/api/observer/evidence', { cache: 'no-store', signal: controller.signal }).then(async response => {
      if (!response.ok) throw Error();
      const result = parse(await response.json());
      if (!controller.signal.aborted) setData(result);
    }).catch(() => { if (!controller.signal.aborted) setError(true); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [run, revision]);
  return { data, error, loading, refresh: () => setRevision(n => n + 1) };
}
export function relation(data: Evidence | null, snapshot: Snapshot | null, run: string | null): string {
  if (data?.status !== 'VERIFIED' || !data.artifact || !data.verdict) return 'unverified';
  if (data.run_id !== run) return 'run';
  if (!snapshot) return 'unobserved';
  if (snapshot.commerce?.receipt_status === 'UNAVAILABLE') return 'incomplete';
  const a = data.artifact, v = data.verdict;
  if (!sameGoal(a.goal, snapshot.goal) || a.budget !== snapshot.balance.budget) return 'goal';
  if (a.captured_at_tick > snapshot.tick) return 'ahead';
  if (v.spent === undefined || !v.received_on_time) return 'incomplete';
  if (v.spent !== snapshot.balance.spent || v.reserved !== snapshot.balance.reserved || !same(v.received_on_time, snapshot.inventory)) return 'state';
  return 'matches';
}
export function evidenceTitle(data: Evidence | null, snapshot: Snapshot | null, run: string | null): string {
  if (relation(data, snapshot, run) === 'matches' && data?.verdict) return labels[data.verdict.status];
  return 'Awaiting independent ledger verification';
}
export function EvidencePanel({ evidence, snapshot, run, fresh }: { evidence: ReturnType<typeof useEvidence>; snapshot: Snapshot | null; run: string | null; fresh: boolean }) {
  const { data, error, loading, refresh } = evidence;
  const match = relation(data, snapshot, run), artifact = data?.artifact, verdict = data?.verdict;
  const relationLabel: Record<string, string> = { run: 'The current run and evidence run differ.', unobserved: 'Evidence will be compared when an observation arrives.', goal: 'The current goal or budget differs from the evidence.', ahead: 'The evidence was captured after the current observation.', incomplete: 'Insufficient ledger values for comparison.', state: 'Ledger values differ between the evidence and current observation.', matches: fresh ? 'Matches the current observed values.' : 'Matches the last observed values. Live state is unconfirmed.' };
  return <section className="panel evidence-panel" aria-label="Independent evidence"><div className="panel-heading"><div><span className="eyebrow">05 / INDEPENDENT EVIDENCE</span><h2>Independent ledger verdict</h2></div><button className="reconnect" onClick={refresh} disabled={loading}>{loading ? 'Verifying…' : 'Reverify evidence'}</button></div>
    <div className="evidence-body" data-testid="evidence-result">
      {loading ? <p>Rechecking the selected original evidence.</p> : error ? <p>Cannot connect to the verification API. Previous success is not reused.</p> : data?.status !== 'VERIFIED' ? <p>{reasons[data?.reason ?? ''] ?? 'Cannot verify independent evidence.'}</p> : <>
        <div className="evidence-verdict"><strong>{labels[verdict!.status]}</strong><code>{verdict!.status}</code><span>{relationLabel[match]}</span></div>
        <dl className="evidence-facts"><div><dt>Evidence run</dt><dd>{artifact!.run_id}</dd></div><div><dt>Evidence capture time</dt><dd>tick {artifact!.captured_at_tick}</dd></div><div><dt>Ledger spent / reserved</dt><dd>{verdict!.spent ?? '—'} / {verdict!.reserved ?? '—'} credits</dd></div><div><dt>File SHA-256</dt><dd><code>{artifact!.sha256}</code></dd></div><div><dt>Verifier SHA-256</dt><dd><code>{data.verifier!.sha256}</code></dd></div></dl>
        {!!verdict!.errors.length && <details><summary>Verification errors: {verdict!.errors.length}</summary><ul>{verdict!.errors.map((e, i) => <li key={i}>{e}</li>)}</ul></details>}
        <p className="evidence-scope">The selected Medusa synthetic payment and delivery records were reverified. The verdict applies at evidence capture, not to the current state or real goods. Hashes identify the selected files.</p>
      </>}
    </div>
  </section>;
}
