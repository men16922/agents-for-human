import { useEffect, useState } from 'react';
import { integer, type Snapshot } from './observation';

type Event = { kind: 'decision_basis' | 'effect_blocked' | 'effect_rechecked' | 'read_error'; at: number; tick?: number; replan?: number; effect?: 'orders' | 'payments'; reason?: string };
type RecordSummary = {
  goal: Snapshot['goal']; budget: number; spec_sha256: string; reaction_limit: number | null;
  runtime_status: string | null; stop_reason: string | null;
  audit: { basis: { tick: number; replan: number } | null; replans: number; blocked_effects: number; effect_rechecks: number; read_errors: number; cursor: number; version: number; partial_tail: boolean; rows: number; recent: Event[] };
};
export type Execution = { status: 'UNCONFIGURED' | 'PENDING' | 'REJECTED' | 'PROVISIONAL' | 'SEALED'; reason: string | null; run_id: string | null; checked_at: number; read_only: true; transaction_verified: false; model_efficacy_verified: false; execution: RecordSummary | null };
const reasons: Record<string, string> = {
  OBSERVATION_CHANGED_REPLAN: 'Observation changed after decision', OBSERVATION_DEADLINE_REACHED: 'Observed deadline reached',
  OBSERVATION_REPLAN_LIMIT: 'Replanning limit reached', OBSERVATION_UNAVAILABLE_RECHECK: 'Observation unknown before action',
  QUOTE_EXPIRED_RECHECK: 'Quote expired', QUOTE_BASIS_CHANGED_RECHECK: 'Quote basis changed',
  OBSERVATION_UNAVAILABLE: 'Observation read failed', OBSERVATION_STALE: 'Observation delayed', DEADLINE: 'Deadline reached',
  MODEL_CALL_LIMIT: 'Model call limit reached', COST_LIMIT: 'Cost limit reached', TOKEN_LIMIT: 'Token limit reached',
  TOOL_CALL_LIMIT: 'Tool call limit reached', USAGE_UNKNOWN: 'Usage unknown',
  PRIOR_USAGE_UNRESOLVED: 'Prior usage unresolved', INPUT_ESTIMATE_UNAVAILABLE: 'Input estimate unavailable',
  INPUT_TOKEN_LIMIT: 'Input token limit reached', ESTIMATED_COST_LIMIT: 'Estimated cost limit reached', TOTAL_TOKEN_LIMIT: 'Shared token limit reached',
  OBSERVATION_READ_FAILED: 'Latest observation read failed', HTTP_RUN_CONTRACT_CHANGED: 'Run goal or budget changed',
  EXECUTION_INPUT_CHANGED: 'Frozen execution input changed', FRESH_EXTERNAL_RUN_REQUIRED: 'Fresh external run required',
};
const reasonLabel = (value: string | null | undefined) => value ? reasons[value] ?? 'Other stop reason' : 'Not recorded';
const runtime: Record<string, string> = { COMPLETED: 'Execution finished', INCOMPLETE: 'Finished incomplete', LIMITED: 'Stopped at a limit', ERROR: 'Stopped with an error' };
export function parseExecution(value: Execution): Execution {
  if (!value || !['UNCONFIGURED', 'PENDING', 'REJECTED', 'PROVISIONAL', 'SEALED'].includes(value.status) || value.read_only !== true || value.transaction_verified !== false || value.model_efficacy_verified !== false || !Number.isFinite(value.checked_at)) throw Error();
  const e = value.execution;
  if (value.status === 'SEALED' || value.status === 'PROVISIONAL') {
    if (!e || typeof value.run_id !== 'string' || !/^[a-f0-9]{64}$/.test(e.spec_sha256) || !e.goal?.items || typeof e.goal.recipient !== 'string') throw Error();
    integer(e.budget, 1); integer(e.goal.deadline_tick, 1);
    if (!Object.keys(e.goal.items).length) throw Error();
    for (const n of Object.values(e.goal.items)) integer(n, 1);
    if (e.reaction_limit !== null && (integer(e.reaction_limit, 1) > 32)) throw Error();
    if (value.status === 'SEALED' ? !Object.hasOwn(runtime, e.runtime_status ?? '') : e.runtime_status !== null || e.stop_reason !== null) throw Error();
    if (e.stop_reason !== null && typeof e.stop_reason !== 'string') throw Error();
    const a = e.audit;
    for (const key of ['replans', 'blocked_effects', 'effect_rechecks', 'read_errors', 'cursor', 'version', 'rows'] as const) integer(a[key]);
    if (a.replans > (e.reaction_limit ?? 0) || typeof a.partial_tail !== 'boolean' || (value.status === 'SEALED' && a.partial_tail)) throw Error();
    if (a.basis !== null) { integer(a.basis.tick); integer(a.basis.replan); if (a.basis.replan !== a.replans) throw Error(); }
    if (!Array.isArray(a.recent) || a.recent.length > 12) throw Error();
    for (const event of a.recent) {
      if (!['decision_basis', 'effect_blocked', 'effect_rechecked', 'read_error'].includes(event.kind) || !Number.isFinite(event.at)) throw Error();
      if (event.kind !== 'read_error') integer(event.tick);
      if (event.kind === 'decision_basis') integer(event.replan);
      if (['effect_blocked', 'effect_rechecked'].includes(event.kind) && !['orders', 'payments'].includes(event.effect ?? '')) throw Error();
    }
  } else if (e !== null) throw Error();
  return value;
}

export function ExecutionPanel({ run, snapshot }: { run: string | null; snapshot: Snapshot | null }) {
  const [data, setData] = useState<Execution | null>(null), [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setData(null); setError(false);
    async function refresh() {
      try {
        const response = await fetch('/api/observer/execution', { cache: 'no-store', signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]) });
        if (!response.ok) throw Error();
        const result = parseExecution(await response.json());
        if (!controller.signal.aborted) { setData(result); setError(false); }
      } catch { if (!controller.signal.aborted) { setData(null); setError(true); } }
      finally { if (!controller.signal.aborted) timer = setTimeout(refresh, 2000); }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [run, revision]);
  const e = data?.execution, a = e?.audit;
  const scoped = !!e && data.run_id === run && !!snapshot && e.budget === snapshot.balance.budget && e.goal.recipient === snapshot.goal.recipient && e.goal.deadline_tick === snapshot.goal.deadline_tick && Object.keys(e.goal.items).length === Object.keys(snapshot.goal.items).length && Object.entries(e.goal.items).every(([k, n]) => snapshot.goal.items[k] === n);
  return <section className="panel execution-panel" aria-label="Executor reaction record">
    <div className="panel-heading"><div><span className="eyebrow">07 / EXECUTOR RECORD</span><h2>Decisions and actions</h2></div><button className="reconnect" onClick={() => setRevision(n => n + 1)}>Refresh execution</button></div>
    <div data-testid="execution-result">
      {error ? <p>Cannot verify the execution record. Previous results are hidden.</p> : !data ? <p>Checking execution record…</p> : !e ? <p>{data.status === 'UNCONFIGURED' ? 'No execution record selected.' : data.status === 'PENDING' ? 'Waiting for the selected execution file.' : 'Execution scope or record validation failed.'}</p> : !scoped ? <p>Cannot match this record to the observed run, goal and budget.</p> : <>
        <div className="evidence-verdict"><strong>{data.status === 'SEALED' ? 'Sealed record · file integrity verified' : 'Provisional record · completion unconfirmed'}</strong><span>{data.status === 'SEALED' ? runtime[e.runtime_status!] : 'A record exists. This does not establish whether the execution is still running.'}</span></div>
        <dl className="evidence-facts">
          <div><dt>Replanning configuration</dt><dd>{e.reaction_limit === null ? 'Disabled' : `Up to ${e.reaction_limit} replans`}</dd></div>
          <div><dt>Latest decision basis</dt><dd>{a!.basis ? `tick ${a!.basis.tick}` : 'Not recorded'}</dd></div>
          <div><dt>Replans / blocked actions</dt><dd data-testid="reaction-counts">{a!.replans} / {a!.blocked_effects}</dd></div>
          <div><dt>Pre-action checks / read failures</dt><dd>{a!.effect_rechecks} / {a!.read_errors}</dd></div>
          <div><dt>Executor stream position</dt><dd>v{a!.version} · cursor {a!.cursor}</dd></div>
          <div><dt>Stop reason</dt><dd>{data.status === 'SEALED' ? reasonLabel(e.stop_reason) : 'Completion unconfirmed'}</dd></div>
        </dl>
        {a!.partial_tail && <p>The unfinished final line is excluded from the summary.</p>}
        <ol className="reaction-events">{a!.recent.map((event, i) => <li key={i}><span>{event.tick === undefined ? 'Reading' : `tick ${event.tick}`}</span><strong>{event.kind === 'decision_basis' ? event.replan === 0 ? 'Initial decision basis' : `Replan ${event.replan}` : event.kind === 'read_error' ? 'Observation read failed' : `${event.effect === 'orders' ? 'Order' : 'Payment'} ${event.kind === 'effect_blocked' ? 'blocked' : 'rechecked before action'}`}</strong>{event.reason && <span>{reasonLabel(event.reason)}</span>}</li>)}</ol>
        <p className="evidence-scope">Latest 12 key events · refreshed every 2 seconds. Replans count recorded call preparations, not model effectiveness. File integrity does not establish transaction success; consult the independent ledger verdict.</p>
      </>}
    </div>
  </section>;
}
