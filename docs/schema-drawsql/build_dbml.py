from pathlib import Path
import re,json
P=Path(__file__).resolve().parent
GROUPS={
'oltp':[
('Catalog_Seller','#8b5cf6',['categories','sellers','products']),
('Customer_Order','#3b82f6',['customers','customer_addresses','channels','payment_methods','checkouts','checkout_lines','orders','order_items','order_item_promotions','payments','refunds','returns','product_reviews']),
('Warehouse_Logistics','#10b981',['warehouses','carriers','inventory_levels','inventory_movements','inventory_daily_balance','shipments','delivery_attempts']),
('Marketing','#f59e0b',['marketing_campaigns','ad_spend_logs','promotions','promotion_usages']),
('Web_Analytics','#06b6d4',['sessions','page_events','cart_items']),
('Finance','#ec4899',['seller_commission_rates','seller_payouts','seller_payout_items'])],
'dw':[
('Facts','#f43f5e',['fact_order_item','fact_inventory_snapshot','fact_ad_spend']),
('Time_Channel','#3b82f6',['dim_date','dim_month','dim_channel']),
('Product_Category','#8b5cf6',['dim_product','dim_category','bridge_category_hierarchy']),
('Seller_History','#f59e0b',['dim_seller','dim_seller_tier_t3']),
('Customer_Profile','#06b6d4',['dim_customer','dim_customer_profile']),
('Campaign_Promotion','#ec4899',['dim_campaign','dim_promotion','dim_promotion_group','bridge_promotion_group']),
('Warehouse_Payment','#10b981',['dim_warehouse','dim_payment_method'])]}
def split(s):
 a=[];start=depth=0;quote=False
 for i,c in enumerate(s):
  if c=="'": quote=not quote
  if not quote:
   if c=='(':depth+=1
   if c==')':depth-=1
   if c==',' and depth==0:a.append(s[start:i].strip());start=i+1
 a.append(s[start:].strip());return a
for kind,groups in GROUPS.items():
 s=(P/f'{kind}_drawsql.sql').read_text();tables={};refs=[]
 for name,body in re.findall(r'CREATE TABLE\s+([\w.]+)\s*\((.*?)\)\s*;',s,re.S):
  t={'name':name.split('.')[-1],'columns':[],'pk':[],'unique':[]}
  for line in split(body):
   if re.match(r'^(CONSTRAINT|CHECK|UNIQUE|PRIMARY|FOREIGN)\b',line,re.I):
    pk=re.search(r'PRIMARY KEY\s*\((.*?)\)',line,re.I)
    uq=re.search(r'UNIQUE\s*\((.*?)\)',line,re.I)
    if pk:t['pk']+= [x.strip() for x in pk[1].split(',')]
    if uq:t['unique'].append([x.strip() for x in uq[1].split(',')])
    continue
   m=re.match(r'(\w+)\s+(.*)',line,re.S);col,rest=m.groups()
   typ=re.split(r'\s+(?:NOT NULL|PRIMARY KEY|UNIQUE|DEFAULT|REFERENCES|CHECK)\b',rest,flags=re.I)[0].strip()
   t['columns'].append({'name':col,'type':typ,'nullable':not('NOT NULL' in rest or 'PRIMARY KEY' in rest)})
   if 'PRIMARY KEY' in rest:t['pk'].append(col)
   if 'UNIQUE' in rest:t['unique'].append([col])
   fk=re.search(r'REFERENCES\s+([\w.]+)\s*\((\w+)\)',rest,re.I)
   if fk:refs.append({'from':t['name'],'column':col,'to':fk[1].split('.')[-1],'target':fk[2]})
  tables[t['name']]=t
 for table,stmt in re.findall(r'ALTER TABLE ONLY\s+[\w]+\.(\w+)\s+ADD CONSTRAINT\s+\w+\s+(.*?);',s,re.S):
  pk=re.search(r'PRIMARY KEY\s*\((.*?)\)',stmt)
  uq=re.search(r'UNIQUE\s*\((.*?)\)',stmt)
  if pk:tables[table]['pk'] += [x.strip() for x in pk[1].split(',')]
  if uq:tables[table]['unique'].append([x.strip() for x in uq[1].split(',')])
  fk=re.search(r'FOREIGN KEY\s*\((\w+)\)\s+REFERENCES\s+[\w]+\.(\w+)\s*\((\w+)\)',stmt)
  if fk:refs.append({'from':table,'column':fk[1],'to':fk[2],'target':fk[3]})
 assert sorted(tables)==sorted(t for _,_,ts in groups for t in ts)
 lines=['Project ecommerce_'+kind+' {',' database_type: \'PostgreSQL\'','}']
 for title,color,names in groups:
  for name in names:
   t=tables[name];lines.append(f'Table {name} [headercolor: {color}] {{')
   for c in t['columns']:
    attrs=[]
    if len(t['pk'])==1 and c['name'] in t['pk']:attrs.append('pk')
    if not c['nullable']:attrs.append('not null')
    if [c['name']] in t['unique']:attrs.append('unique')
    ty=c['type'];ty='"'+ty+'"' if ' ' in ty else ty
    lines.append(f'  {c["name"]} {ty}'+(' ['+', '.join(attrs)+']' if attrs else ''))
   composite=[(t['pk'],'pk')] if len(t['pk'])>1 else []
   composite += [(u,'unique') for u in t['unique'] if len(u)>1]
   if composite:
    lines.append('  indexes {')
    for cols,attr in composite:lines.append('    ('+', '.join(cols)+') ['+attr+']')
    lines.append('  }')
   lines.append('}\n')
  lines.append(f'TableGroup {title} [color: {color}] {{\n  '+'\n  '.join(names)+'\n}\n')
 for r in refs:lines.append(f'Ref: {r["from"]}.{r["column"]} > {r["to"]}.{r["target"]}')
 (P/f'{kind}_grouped.dbml').write_text('\n'.join(lines)+'\n')
 (P/f'{kind}_metadata.json').write_text(json.dumps({'groups':groups,'tables':tables,'relationships':refs},ensure_ascii=False,indent=2)+'\n')
 print(kind,len(tables),'tables',sum(len(t['columns']) for t in tables.values()),'columns',len(refs),'FK')
