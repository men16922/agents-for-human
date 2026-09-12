/** Browser projection of the customer observation contract. No transaction commands. */
export type Snapshot = {
  run_id: string; tick: number; clock_mode: string;
  goal: { items: Record<string, number>; deadline_tick: number; recipient: string };
  inventory: Record<string, number>;
  balance: { budget: number; spent: number; reserved: number; available: number };
  suppliers: string[];
  commerce?: CommerceDetails;
};
export type Offer = { supplier: string; item: string; status: string; stock: number | null; unit_price: number | null; currency: string | null; inventory_managed: boolean | null; backorder: boolean | null };
export type Order = { id: string; run_id: string; supplier: string; items: Record<string, number>; amount: number; status: string; payment_status: string; created_tick: number };
export type CommerceDetails = { receipt_status: string; catalog: { status: string; offers: Offer[]; source: string }; orders: { status: string; total: number; truncated: boolean; items: Order[] } };
export type Observation = { event_id: string; run_id: string; version: number; observed_at: number; event_type: string; snapshot: Snapshot };
export type Frame = { event: string; id?: string; data: string };
const object = (v: unknown): Record<string, unknown> => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw Error('INVALID_OBJECT');
  return v as Record<string, unknown>;
};
export const integer = (v: unknown, min = 0): number => {
  if (typeof v !== 'number' || !Number.isSafeInteger(v) || v < min) throw Error('INVALID_INTEGER');
  return v;
};
const string = (v: unknown): string => {
  if (typeof v !== 'string' || !v.length || v.length > 256) throw Error('INVALID_STRING');
  return v;
};
const quantities = (v: unknown, min = 0): Record<string, number> => Object.fromEntries(
  Object.entries(object(v)).map(([k, n]) => [string(k), integer(n, min)])
);
function snapshot(value: unknown, run: string): Snapshot {
  const s = object(value), goal = object(s.goal), b = object(s.balance);
  if (s.run_id !== run) throw Error('RUN_SCOPE_DENIED');
  const balance = { budget: integer(b.budget), spent: integer(b.spent), reserved: integer(b.reserved), available: integer(b.available) };
  if (balance.budget - balance.spent - balance.reserved !== balance.available) throw Error('INVALID_BALANCE');
  if (!Array.isArray(s.suppliers) || s.suppliers.length > 30) throw Error('INVALID_SUPPLIERS');
  const items = quantities(goal.items, 1);
  if (!Object.keys(items).length || Object.keys(items).length > 30) throw Error('INVALID_GOAL');
  const result: Snapshot = { run_id: run, tick: integer(s.tick), clock_mode: string(s.clock_mode),
    goal: { items, deadline_tick: integer(goal.deadline_tick, 1), recipient: string(goal.recipient) },
    balance, inventory: quantities(s.inventory), suppliers: s.suppliers.map(string) };
  if (s.commerce !== undefined) result.commerce = commerce(s.commerce, result);
  return result;
}
function commerce(value: unknown, snapshot: Snapshot): CommerceDetails {
  const c = object(value), cat = object(c.catalog), orders = object(c.orders);
  if (!['OBSERVED', 'UNAVAILABLE'].includes(String(c.receipt_status)) || !['OBSERVED', 'PARTIAL', 'UNAVAILABLE'].includes(String(cat.status)) || cat.source !== 'medusa-store-sales-channel' || !Array.isArray(cat.offers) || cat.offers.length > 100 || !Array.isArray(orders.items) || orders.items.length > 50 || !['OBSERVED', 'PARTIAL'].includes(String(orders.status))) throw Error('INVALID_COMMERCE');
  const seen = new Set<string>();
  const offers = cat.offers.map(value => {
    const o = object(value), supplier = string(o.supplier), item = string(o.item), key = supplier + ':' + item;
    if (seen.has(key) || !snapshot.suppliers.includes(supplier) || !Object.hasOwn(snapshot.goal.items, item) || !['OBSERVED', 'UNAVAILABLE'].includes(String(o.status))) throw Error('INVALID_OFFER');
    seen.add(key);
    for (const f of ['inventory_managed', 'backorder']) if (o[f] !== null && typeof o[f] !== 'boolean') throw Error('INVALID_OFFER');
    if (o.currency !== null && o.currency !== 'usd') throw Error('INVALID_OFFER');
    return { supplier, item, status: String(o.status), stock: o.stock === null ? null : integer(o.stock), unit_price: o.unit_price === null ? null : integer(o.unit_price), currency: o.currency, inventory_managed: o.inventory_managed, backorder: o.backorder } as Offer;
  });
  const ids = new Set<string>();
  const items = orders.items.map(value => {
    const o = object(value), id = string(o.id), supplier = string(o.supplier);
    if (o.run_id !== snapshot.run_id || ids.has(id) || !snapshot.suppliers.includes(supplier) || !['ACCEPTED', 'PAID', 'FULFILLING', 'DELIVERED', 'UNKNOWN'].includes(String(o.status)) || !['NOT_STARTED', 'RESERVED', 'SETTLED', 'UNKNOWN'].includes(String(o.payment_status))) throw Error('INVALID_ORDER');
    ids.add(id);
    const items = quantities(o.items, 1);
    if (Object.keys(items).some(k => !Object.hasOwn(snapshot.goal.items, k))) throw Error('INVALID_ORDER');
    return { id, run_id: snapshot.run_id, supplier, items, amount: integer(o.amount), status: String(o.status), payment_status: String(o.payment_status), created_tick: integer(o.created_tick) };
  });
  const total = integer(orders.total);
  if (total < items.length || orders.truncated !== (total > items.length)) throw Error('INVALID_ORDERS');
  return { receipt_status: String(c.receipt_status), catalog: { status: String(cat.status), source: String(cat.source), offers }, orders: { status: String(orders.status), total, truncated: orders.truncated as boolean, items } };
}
const canonical = (v: unknown): string => JSON.stringify(v, (_, value) =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) : value);

export class Projection {
  cursor = 0;
  version = 0;
  snapshot: Snapshot | null = null;
  observedAt: number | null = null;
  private seen = new Map<string, string>();
  constructor(readonly run: string) {}
  apply(value: unknown): string {
    const delivery = object(value), e = object(delivery.event);
    const cursor = integer(delivery.cursor), version = integer(e.version, 1), id = string(e.event_id);
    if (e.run_id !== this.run) throw Error('RUN_SCOPE_DENIED');
    if (typeof e.observed_at !== 'number' || !Number.isFinite(e.observed_at) || e.observed_at < 0) throw Error('INVALID_TIMESTAMP');
    string(e.event_type);
    const next = snapshot(e.snapshot, this.run), encoded = canonical(e);
    if (this.seen.has(id) && this.seen.get(id) !== encoded) throw Error('EVENT_CONTENT_CONFLICT');
    if (version === this.version && canonical(next) !== canonical(this.snapshot)) throw Error('OBSERVATION_VERSION_CONFLICT');
    const result = this.seen.has(id) ? 'duplicate' : version <= this.version ? 'old' : 'applied';
    this.seen.set(id, encoded);
    if (this.seen.size > 1000) this.seen.delete(this.seen.keys().next().value!);
    if (version > this.version) { this.snapshot = next; this.version = version; this.observedAt = e.observed_at; }
    this.cursor = Math.max(cursor, this.cursor);
    return result;
  }
  reset(value: unknown): void {
    const batch = object(value), cursor = integer(batch.next_cursor);
    if (batch.run_id !== this.run || batch.reset !== true || cursor < this.cursor) throw Error('INVALID_RESET');
    if (batch.snapshot_event !== null) this.apply({ cursor, event: batch.snapshot_event });
    this.cursor = cursor;
  }
}

/** Incremental SSE framing, including CRLF split across network chunks. */
export class SSEDecoder {
  private buffer = '';
  push(text: string): Frame[] {
    this.buffer += text;
    if (this.buffer.length > 1_048_576) throw Error('STREAM_TOO_LARGE');
    const frames: Frame[] = [];
    let boundary: RegExpExecArray | null;
    while ((boundary = /\r?\n\r?\n/.exec(this.buffer))) {
      const block = this.buffer.slice(0, boundary.index);
      this.buffer = this.buffer.slice(boundary.index + boundary[0].length);
      let event = 'message', id: string | undefined;
      const data: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith(':')) continue;
        const at = line.indexOf(':'), key = at < 0 ? line : line.slice(0, at);
        const value = at < 0 ? '' : line.slice(at + 1).replace(/^ /, '');
        if (key === 'event') event = value;
        if (key === 'id') { if (value.includes('\0')) throw Error('INVALID_CURSOR'); id = value; }
        if (key === 'data') data.push(value);
      }
      if (data.length) frames.push({ event, id, data: data.join('\n') });
    }
    return frames;
  }
}
export const frameCursor = (frame: Frame): number => {
  if (!frame.id || !/^[0-9]{1,19}$/.test(frame.id)) throw Error('INVALID_CURSOR');
  return integer(Number(frame.id));
};
