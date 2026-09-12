import type { Snapshot } from './observation';
const name = (s: string) => ({ tent: 'Tents', light: 'Lights' }[s] ?? s);
const status: Record<string, string> = { ACCEPTED: 'Accepted', PAID: 'Payment completed', FULFILLING: 'Delivery in progress', DELIVERED: 'Delivery confirmed', UNKNOWN: 'Unknown', NOT_STARTED: 'Not paid', RESERVED: 'Budget reserved', SETTLED: 'Settled' };
export function stockLabel(s: Snapshot | null, supplier: string) {
  if (!s?.commerce) return 'Stock data unavailable';
  const offers = s.commerce.catalog.offers.filter(o => o.supplier === supplier);
  if (!offers.length) return 'Stock status unknown';
  return offers.map(o => `${name(o.item)} ${o.status !== 'OBSERVED' || o.stock === null ? '—' : o.stock}`).join(' · ');
}
export function Commerce({ snapshot }: { snapshot: Snapshot | null }) {
  const c = snapshot?.commerce;
  return <section className="commerce-grid" aria-label="Supplier and order observations"><div className="panel"><span className="eyebrow">SUPPLIER AVAILABILITY</span><h2>Supplier availability</h2><p className="commerce-caption">Values at the last sales-channel query. Unit prices are not confirmed quotes including shipping.</p>
    {!c?.catalog.offers.length ? <p className="empty">{c ? 'Stock status unknown' : 'Supplier details unavailable'}</p> : <div className="table-scroll"><table><thead><tr><th>Supplier / item</th><th>Available stock</th><th>Unit price</th></tr></thead><tbody>{c.catalog.offers.map(o => <tr key={`${o.supplier}-${o.item}`}><td>{o.supplier} · {name(o.item)}</td><td data-testid={`stock-${o.supplier}-${o.item}`}>{o.status !== 'OBSERVED' ? 'Unknown' : o.inventory_managed === false ? 'Stock not managed' : o.stock ?? 'Unknown'}{o.backorder === true && <small>Backorders allowed</small>}</td><td>{o.status === 'OBSERVED' && o.unit_price !== null ? `${o.unit_price} credits` : 'Unknown'}</td></tr>)}</tbody></table></div>}
    {c?.catalog.status === 'PARTIAL' && <p className="commerce-caption">Current values are unavailable for some items.</p>}
    </div><div className="panel"><div className="panel-heading"><div><span className="eyebrow">RUN ORDERS</span><h2>Run orders</h2></div><span className="tick">{c ? `${c.orders.total} orders` : 'Unavailable'}</span></div>
      {!c?.orders.items.length ? <p className="empty">{c ? 'No orders accepted for this run.' : 'Order details unavailable'}</p> : <ol className="order-list">{c.orders.items.map(o => <li key={o.id}><div className="order-heading"><strong>Supplier {o.supplier}</strong><span data-testid="order-status">{status[o.status]}</span></div><p>{Object.entries(o.items).map(([k, q]) => `${name(k)} ${q}`).join(' · ')}<b>{o.amount} credits</b></p><div className="order-meta"><span data-testid="order-payment">{status[o.payment_status]}</span><span>Accepted tick {o.created_tick}</span></div><code>{o.id}</code></li>)}</ol>}
      {c?.orders.truncated && <p className="commerce-caption">Showing the latest 50 of {c.orders.total} orders.</p>}
      {c?.orders.status === 'PARTIAL' && <p className="commerce-caption">Failed reads are shown as unknown. This view does not retry purchases or payments.</p>}
    </div></section>;
}
