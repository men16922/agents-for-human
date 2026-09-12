import json,sys,threading,time,hashlib
from copy import deepcopy
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path.cwd()/'scripts/commerce'))
from model_session import Session,ROOT
from rehearsal.commerce.gateway import StoreAPI,ORDER_FIELDS
from rehearsal.commerce.seller import read_rows
from rehearsal.world.storage import identifier
from rehearsal.commerce.model_runner import write

def main():
 folder=ROOT/'.local/evaluation'/identifier('delivery-capture');folder.mkdir()
 case=json.loads((ROOT/'scenarios/normal-v1.json').read_text());case['goal']['deadline_tick']=120
 session=Session(fixture=True,case=case);result={'passed':False,'samples':[],'counts':{},'source_sha256':hashlib.sha256((ROOT/'src/rehearsal/commerce/gateway.py').read_bytes()).hexdigest()}
 try:
  path=session.start();result['session']=str(path.relative_to(ROOT))
  buyer=session.buyer;quote=buyer.get_quotes('A',{'tent':3,'light':6});order=buyer.create_order(quote['id'],'capture-buy');buyer.authorize_payment(order['id'],'capture-pay')
  result['local_order']=order['id']
  deadline=time.monotonic()+25
  oid=None
  while time.monotonic()<deadline and not oid:
   row=next(r for r in read_rows(Path(session.run['directory'])/'medusa.sqlite3','purchases') if r['id']==order['id']);oid=row['external_id']
   if not oid:time.sleep(.05)
  assert oid
  result['external_order']=oid
  lock=threading.Lock();done=threading.Event()
  def poll(index):
   store=StoreAPI(session.run['store_token'],session.run['publishable_key']);seen=set()
   try:
    while time.monotonic()<deadline and not done.is_set():
     begin=time.time();raw=store.call('GET',f'/store/orders/{oid}?fields={ORDER_FIELDS}')['order'];end=time.time()
     quantities=[i['detail']['delivered_quantity'] for i in raw['items']]
     state='consistent-delivered' if raw['fulfillment_status']=='delivered' and all(i['detail']['delivered_quantity']==i['quantity'] for i in raw['items']) else 'split-delivered' if raw['fulfillment_status']=='delivered' else raw['fulfillment_status']
     with lock:
      result['counts'][state]=result['counts'].get(state,0)+1
      if state not in seen or state=='split-delivered':result['samples'].append({'consumer':index,'begin':begin,'end':end,'state':state,'order':raw})
      seen.add(state)
      if state=='consistent-delivered' and result['counts'][state]>=4:done.set()
     time.sleep(.005)
   finally:store.close()
  with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(poll,range(4)))
  result['passed']=bool(result['counts'].get('split-delivered')) and bool(result['counts'].get('consistent-delivered'))
 finally:
  session.close('DELIVERY_CAPTURE_FINISHED')
  result['final_session']=session.record
  write(folder/'capture.json',result)
  print(folder, result['counts'], 'SPLIT_CAPTURED',result['passed'])
main()
