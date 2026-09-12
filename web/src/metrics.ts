/** Per-browser-session measurement. Export denominators, never infer unobserved deliveries. */
export type Outcome = 'applied' | 'duplicate' | 'old' | 'reset_applied' | 'reset_unchanged';
export type Sample = { sequence: number; cursor: number; event_id: string; event_type: string; version: number; outcome: Outcome;
  observed_ms: number | null; poll_started_ms: number | null; poll_elapsed_ms: number | null; published_ms: number | null;
  received_ms: number; received_mono_ms: number; received_visible: boolean; render_ms: number | null; render_mono_ms: number | null;
  render_status: 'pending' | 'rendered' | 'superseded' | 'not_applied' | 'hidden'; };
export type Percentiles = { n: number; p50: number | null; p95: number | null; max: number | null; excluded: Record<string, number> };
type PollStats = { process_id: string; attempted: number; completed: number; failed: number; unchanged: number; in_flight: boolean };
const ms = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= Number.MAX_SAFE_INTEGER / 1000 ? value * 1000 : null;
export function distribution(values: number[], excluded: Record<string, number> = {}): Percentiles {
  const sorted = [...values].sort((a, b) => a - b);
  const at = (q: number) => sorted.length ? sorted[Math.max(0, Math.ceil(q * sorted.length) - 1)] : null;
  return { n: sorted.length, p50: at(.5), p95: at(.95), max: at(1), excluded };
}
export class ObservationMetrics {
  readonly started_ms: number;
  rows: Sample[] = [];
  counters: Record<string, number> = { frames: 0, observation: 0, snapshot: 0, status: 0, applied: 0, duplicate: 0, old: 0,
    reset_applied: 0, reset_unchanged: 0, invalid: 0, connection_attempts: 0, disconnects: 0, manual_reconnects: 0,
    evicted: 0, unknown_frames: 0, bridge_error: 0, unseen_cursors: 0, reset_skipped_cursors: 0, server_periods_evicted: 0 };
  private periods = new Map<string, { first: PollStats; last: PollStats }>();
  constructor(readonly run: string, readonly capacity = 2000, started = Date.now()) {
    if (!Number.isSafeInteger(capacity) || capacity < 1 || capacity > 2000) throw Error('INVALID_METRIC_CAPACITY');
    this.started_ms = started;
  }
  count(name: string) { const key = Object.hasOwn(this.counters, name) ? name : 'unknown_frames'; this.counters[key]++; }
  server(value: unknown) {
    if (!value || typeof value !== 'object') return;
    const p = value as PollStats;
    if (typeof p.process_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(p.process_id) || typeof p.in_flight !== 'boolean' || ![p.attempted, p.completed, p.failed, p.unchanged].every(n => Number.isSafeInteger(n) && n >= 0) || p.completed + p.failed + Number(p.in_flight) !== p.attempted || p.unchanged > p.completed) return;
    const previous = this.periods.get(p.process_id);
    if (previous && (p.attempted < previous.last.attempted || p.completed < previous.last.completed || p.failed < previous.last.failed)) return;
    const clean = { process_id: p.process_id, attempted: p.attempted, completed: p.completed, failed: p.failed, unchanged: p.unchanged, in_flight: p.in_flight };
    this.periods.set(p.process_id, { first: previous?.first ?? clean, last: clean });
    if (this.periods.size > 32) { this.periods.delete(this.periods.keys().next().value!); this.count('server_periods_evicted'); }
  }
  receive(event: Record<string, unknown>, cursor: number, published: unknown, outcome: Outcome, previousCursor: number,
    wall = Date.now(), mono = performance.now(), visible = !document.hidden) {
    this.count(outcome);
    const isReset = outcome.startsWith('reset');
    if (isReset) this.counters.reset_skipped_cursors += Math.max(0, cursor - previousCursor);
    else this.counters.unseen_cursors += Math.max(0, cursor - previousCursor - 1);
    const applied = outcome === 'applied' || outcome === 'reset_applied';
    if (applied) for (const row of this.rows) if (row.render_status === 'pending') row.render_status = 'superseded';
    this.rows.push({ sequence: this.counters.observation + this.counters.snapshot, cursor,
      event_id: String(event.event_id), event_type: String(event.event_type), version: Number(event.version), outcome,
      observed_ms: ms(event.observed_at), poll_started_ms: ms(event.poll_started_at), poll_elapsed_ms: ms(event.poll_elapsed_seconds), published_ms: ms(published),
      received_ms: wall, received_mono_ms: mono, received_visible: visible, render_ms: null, render_mono_ms: null,
      render_status: applied ? 'pending' : 'not_applied' });
    if (this.rows.length > this.capacity) { this.rows.shift(); this.count('evicted'); }
  }
  rendered(version: number, wall = Date.now(), mono = performance.now(), visible = !document.hidden) {
    const row = [...this.rows].reverse().find(r => r.version === version && r.render_status === 'pending');
    if (!row) return;
    row.render_ms = wall; row.render_mono_ms = mono;
    row.render_status = visible && row.received_visible ? 'rendered' : 'hidden';
  }
  summary(rows = this.rows) {
    const values: Record<string, number[]> = { poll: [], publication: [], transport: [], render: [], observed_to_render: [], poll_to_render: [] };
    const excluded: Record<string, Record<string, number>> = Object.fromEntries(Object.keys(values).map(k => [k, {}]));
    const add = (key: string, value: number | null, reason = 'missing_timing') => {
      if (value !== null && Number.isFinite(value) && value >= 0) values[key].push(value);
      else { const r = value !== null ? 'clock_order' : reason; excluded[key][r] = (excluded[key][r] ?? 0) + 1; }
    };
    const diff = (end: number | null, start: number | null) => end === null || start === null ? null : end - start;
    const unique = new Set<string>();
    for (const r of rows) {
      if (!unique.has(r.event_id)) { add('poll', r.poll_elapsed_ms); unique.add(r.event_id); }
      add('publication', diff(r.published_ms, r.observed_ms));
      add('transport', diff(r.received_ms, r.published_ms));
      const local = diff(r.render_mono_ms, r.received_mono_ms);
      const wall = diff(r.render_ms, r.received_ms);
      const clockChanged = local !== null && wall !== null && Math.abs(local - wall) > 100;
      if (r.render_status !== 'rendered') {
        for (const k of ['render', 'observed_to_render', 'poll_to_render']) add(k, null, r.render_status);
      } else {
        add('render', local);
        const ordered = r.poll_started_ms === null || r.observed_ms === null || r.poll_started_ms <= r.observed_ms;
        const serverOrder = r.published_ms === null || r.observed_ms === null || r.published_ms >= r.observed_ms;
        const browserOrder = r.published_ms === null || r.received_ms >= r.published_ms;
        const validWall = !clockChanged && ordered && serverOrder && browserOrder;
        add('observed_to_render', validWall ? diff(r.render_ms, r.observed_ms) : -1);
        add('poll_to_render', validWall ? diff(r.render_ms, r.poll_started_ms) : -1);
      }
    }
    return Object.fromEntries(Object.keys(values).map(k => [k, distribution(values[k], excluded[k])])) as Record<string, Percentiles>;
  }
  export(now = Date.now()) {
    return { schema_version: 1, scope: 'local-browser-observation-latency', run_id: this.run,
      started_ms: this.started_ms, exported_ms: now, capacity: this.capacity, retained: this.rows.length,
      counters: { ...this.counters }, summary: this.summary(), summary_by_event_type: Object.fromEntries(['snapshot.observed', 'state.observed', 'clock.observed', 'delivery.observed'].map(type => [type, this.summary(this.rows.filter(r => r.event_type === type))])), server_periods: [...this.periods.values()], samples: this.rows.map(r => ({ ...r })),
      limits: ['nearest-rank percentiles over retained samples only', 'poll counts distinct observed event IDs; other stages count deliveries or rendered states',
        'wall-clock stages require comparable local clocks; no clock synchronization proof', 'two animation frames after React commit approximate a paint opportunity',
        'no external transaction occurrence timestamp; not end-to-end transaction latency', 'unobserved server intervals and evicted samples are not reconstructed'] };
  }
}
