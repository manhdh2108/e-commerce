from pathlib import Path
import re,json
P=Path(__file__).resolve().parent
O=json.loads((P/'oltp_metadata.json').read_text()); D=json.loads((P/'dw_metadata.json').read_text())
sets={
'oltp_1':('oltp',set('categories sellers products customers customer_addresses channels payment_methods marketing_campaigns ad_spend_logs promotions promotion_usages seller_commission_rates seller_payouts seller_payout_items'.split())),
'oltp_2':('oltp',set('checkouts checkout_lines orders order_items order_item_promotions payments refunds returns product_reviews products sellers customers customer_addresses channels payment_methods'.split())),
'oltp_3':('oltp',set('warehouses carriers inventory_levels inventory_movements inventory_daily_balance shipments delivery_attempts sessions page_events cart_items products orders customers channels marketing_campaigns'.split())),
'dw_1':('dw',set(D['tables'])-{'bridge_category_hierarchy','bridge_promotion_group','dim_seller_tier_t3','dim_promotion'}),
'dw_2':('dw',set('bridge_category_hierarchy bridge_promotion_group dim_category dim_promotion_group dim_promotion dim_seller_tier_t3 dim_seller'.split()))}
for label,(kind,names) in sets.items():
 src=(P/f'{kind}_grouped.dbml').read_text();data=O if kind=='oltp' else D
 out=[f"Project {label} {{\n database_type: 'PostgreSQL'\n}}"]
 for m in re.finditer(r'^Table (\w+) ',src,re.M):
  if m[1] not in names:continue
  depth=0
  for j in range(src.index('{',m.start()),len(src)):
   if src[j]=='{':depth+=1
   if src[j]=='}':
    depth-=1
    if not depth:out.append(src[m.start():j+1]);break
 for title,color,ts in data['groups']:
  selected=[t for t in ts if t in names]
  if selected:out.append(f'TableGroup {title} [color: {color}] {{\n '+'\n '.join(selected)+'\n}')
 for r in data['relationships']:
  if r['from'] in names and r['to'] in names:out.append(f'Ref: {r["from"]}.{r["column"]} > {r["to"]}.{r["target"]}')
 (P/f'{label}.dbml').write_text('\n\n'.join(out))
 print(label,len(names),'tables',sum(r['from'] in names and r['to'] in names for r in data['relationships']),'FK')
manifest={k:{'kind':kind,'tables':sorted(ts)} for k,(kind,ts) in sets.items()}
for kind,data in [('oltp',O),('dw',D)]:
 parts=[ts for k,(ki,ts) in sets.items() if ki==kind]
 assert set.union(*parts)==set(data['tables'])
 missing=[r for r in data['relationships'] if not any(r['from'] in ts and r['to'] in ts for ts in parts)]
 manifest[kind+'_cross_panel']=missing;print(kind,'cross panel FKs',len(missing))
(P/'panels_manifest.json').write_text(json.dumps(manifest,indent=2))
