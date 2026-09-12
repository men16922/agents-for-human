import { useEffect, useRef, useState } from 'react';
import { ObservationMetrics, type Outcome } from './metrics';
import { frameCursor, Projection, SSEDecoder, type Snapshot } from './observation';

type Link = 'connecting' | 'live' | 'disconnected' | 'unconfigured' | 'invalid';
export type View = { run: string | null; snapshot: Snapshot | null; cursor: number; version: number;
  link: Link; lastPoll: number | null; upstreamStale: boolean; observedAt: number | null;
  log: { key: number; label: string; detail: string }[] };
const initial: View = { run: null, snapshot: null, cursor: 0, version: 0, link: 'connecting',
  lastPoll: null, upstreamStale: true, observedAt: null, log: [] };
const labels: Record<string, string> = { applied: 'State applied', duplicate: 'Duplicate ignored', old: 'Older version ignored', reset: 'Snapshot restored' };
export function useObserver() {
  const [view, setView] = useState<View>(initial);
  const [retry, setRetry] = useState(0);
  const projection = useRef<Projection | null>(null);
  const sequence = useRef(0);
  const metrics = useRef<ObservationMetrics | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const signal = controller.signal;
    async function connect() {
      setView(v => ({ ...v, link: 'connecting' }));
      let invalid = false;
      try {
        const response = await fetch('/api/observer/config', { signal, cache: 'no-store' });
        if (!response.ok) throw Error('UNAVAILABLE');
        const config = await response.json();
        if (signal.aborted) return;
        if (config.configured === false) { setView({ ...initial, link: 'unconfigured' }); projection.current = null; metrics.current = null; return; }
        if (config.configured !== true || config.read_only !== true || config.mode !== 'live-observer' || typeof config.run_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(config.run_id)) throw Error('UNAVAILABLE');
        if (signal.aborted) return;
        if (projection.current?.run !== config.run_id) {
          projection.current = new Projection(config.run_id);
          metrics.current = new ObservationMetrics(config.run_id);
          setView({ ...initial, run: config.run_id });
        }
        const p = projection.current!, m = metrics.current!;
        m.count('connection_attempts');
        const stream = await fetch('/api/observer/events', { signal, cache: 'no-store', headers: { 'Last-Event-ID': String(p.cursor) } });
        if (!stream.ok || !stream.body || !stream.headers.get('content-type')?.startsWith('text/event-stream')) throw Error('UNAVAILABLE');
        const reader = stream.body.getReader(), decoder = new TextDecoder('utf-8', { fatal: true }), sse = new SSEDecoder();
        try {
          while (!signal.aborted) {
            const { value, done } = await reader.read();
            if (done) break;
            invalid = true;
            const frames = sse.push(decoder.decode(value, { stream: true }));
            invalid = false;
            for (const frame of frames) {
              if (signal.aborted) return;
              invalid = true; // Fail closed on malformed frames; only explicit retry resumes.
              m.count('frames'); m.count(frame.event);
              const receivedWall = Date.now(), receivedMono = performance.now();
              const data = JSON.parse(frame.data);
              if (frame.event === 'bridge_error') { invalid = false; throw Error('UNAVAILABLE'); }
              if (frame.event === 'status') {
                if (data.run_id !== p.run || typeof data.stale !== 'boolean' || !(data.last_poll === null || typeof data.last_poll === 'number' && Number.isFinite(data.last_poll) && data.last_poll >= 0)) throw Error('INVALID_STATUS');
                m.server(data.poll_stats);
                setView(v => ({ ...v, link: 'live', lastPoll: data.last_poll, upstreamStale: data.stale || !!data.error || !!data.publication_error }));
              } else if (frame.event === 'observation' || frame.event === 'snapshot') {
                const cursor = frameCursor(frame);
                if (cursor !== (frame.event === 'snapshot' ? data.next_cursor : data.cursor)) throw Error('CURSOR_MISMATCH');
                const beforeVersion = p.version, beforeCursor = p.cursor;
                const result = frame.event === 'snapshot' ? (p.reset(data), 'reset') : p.apply(data);
                const outcome: Outcome = result === 'reset' ? (p.version > beforeVersion ? 'reset_applied' : 'reset_unchanged') : result as Outcome;
                const event = frame.event === 'snapshot' ? data.snapshot_event : data.event;
                if (event) m.receive(event, cursor, frame.event === 'snapshot' ? null : data.published_at, outcome, beforeCursor, receivedWall, receivedMono, !document.hidden);
                else { m.count(outcome); m.counters.reset_skipped_cursors += Math.max(0, cursor - beforeCursor); }
                const key = ++sequence.current;
                const state = { snapshot: p.snapshot, cursor: p.cursor, version: p.version, observedAt: p.observedAt };
                const detail = `cursor ${cursor} · v${frame.event === 'snapshot' ? p.version : data.event.version}`;
                setView(v => ({ ...v, link: 'live', ...state,
                  log: [{ key, label: labels[result], detail }, ...v.log].slice(0, 30) }));
              } else throw Error('UNKNOWN_EVENT');
              invalid = false;
            }
          }
        } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
        throw Error('STREAM_ENDED');
      } catch {
        if (signal.aborted) return;
        metrics.current?.count(invalid ? 'invalid' : 'disconnects');
        setView(v => ({ ...v, link: invalid ? 'invalid' : 'disconnected' }));
        if (!invalid) timer = setTimeout(() => void connect(), 1500);
      }
    }
    void connect();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [retry]);
  return { view, metrics: metrics.current, reconnect: () => { metrics.current?.count('manual_reconnects'); setRetry(n => n + 1); } };
}
