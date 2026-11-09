"""Compose official DrawSQL JPG table cards into one complete grouped schema.
Input crops are taken from the five unmodified DrawSQL exports alongside this file.
No paid SVG/JSON export API is used. FK lines come from the structural source metadata.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json, math
P=Path(__file__).resolve().parent
ROOT=P.parent
GEO={
'oltp_1':(80,-20,{
'products':(310,1219,863),'sellers':(500,2132,383),'categories':(120,2222,203),
'marketing_campaigns':(980,573,293),'ad_spend_logs':(980,60,343),'promotions':(1340,453,533),'promotion_usages':(1340,85,293),
'seller_commission_rates':(1840,876,233),'seller_payouts':(1840,403,433),'seller_payout_items':(1840,60,293)}),
'oltp_2':(80,-20,{
'customers':(2100,2545,383),'customer_addresses':(2470,2172,323),'channels':(1550,2262,143),'payment_methods':(990,1709,143),
'checkouts':(1190,2232,203),'checkout_lines':(1190,523,173),'orders':(1910,1439,683),'order_items':(2015,866,523),
'order_item_promotions':(1645,508,203),'payments':(1485,1011,233),'refunds':(2395,60,293),'returns':(2110,403,413),'product_reviews':(2470,478,263)}),
'oltp_3':(120,-20,{
'warehouses':(1560,886,233),'carriers':(2110,931,143),'inventory_levels':(1020,458,313),'inventory_movements':(1380,483,263),
'inventory_daily_balance':(1740,458,313),'shipments':(2100,393,443),'delivery_attempts':(2100,60,283),
'sessions':(340,403,293),'page_events':(520,75,263),'cart_items':(160,60,293)}),
'dw_1':(80,-20,{
'fact_order_item':(120,60,1093),'fact_inventory_snapshot':(480,60,553),'fact_ad_spend':(840,60,373),
'dim_date':(3920,60,563),'dim_month':(3920,673,323),'dim_channel':(3920,1036,203),
'dim_product':(120,1373,673),'dim_category':(490,1518,383),'dim_customer':(1340,60,673),'dim_customer_profile':(1700,60,253),
'dim_warehouse':(2200,60,263),'dim_payment_method':(2560,60,173),'dim_campaign':(3060,60,323),'dim_promotion_group':(3420,60,143)}),
'dw_2':(80,-20,{
'bridge_category_hierarchy':(120,60,223),'bridge_promotion_group':(1660,60,223),'dim_promotion':(1840,333,443),
'dim_seller':(620,60,643),'dim_seller_tier_t3':(980,60,203)})}
FONTS='/usr/share/fonts/truetype/dejavu/'
def font(n,bold=False): return ImageFont.truetype(FONTS+('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'),n)
def pale(c):
 rgb=tuple(int(c[i:i+2],16) for i in (1,3,5));return tuple(round(v*.09+255*.91) for v in rgb)
def card_sources(kind):
 out={}
 for source,(mx,my,ts) in GEO.items():
  if not source.startswith(kind): continue
  im=Image.open(P/(source+'.jpg')).convert('RGB')
  for t,(x,y,h) in ts.items():
   x0=round((x-mx)*1.25+50);y0=round((y-my)*1.25+50)
   out[t]=im.crop((x0,y0,x0+400,y0+round(h*1.25)))
 return out

def compose(kind):
 data=json.loads((ROOT/f'{kind}_metadata.json').read_text())
 cards=card_sources(kind);assert set(cards)==set(data['tables'])
 groups=data['groups'];positions={};group_boxes=[]
 # Different widths reflect the number of tables; all original table cards remain at 100%.
 if kind=='oltp':
  placements=[(0,80,330,2),(1,1350,330,3),(2,3150,330,3),(3,80,None,2),(4,3150,None,2),(5,1350,None,2)]
 else:
  placements=[(0,80,330,3),(1,1690,330,2),(2,2920,330,2),(3,4150,330,2),(4,1690,None,2),(5,2920,None,2),(6,4150,None,2)]
 stack={}
 for idx,gx,gy,ncols in placements:
  name,color,names=groups[idx]
  if gy is None: gy=stack.get(gx,330)+100
  width=ncols*400+(ncols-1)*100+120
  heights=[gy+120]*ncols
  # Preserve domain sequence while balancing vertical space.
  for t in names:
   col=min(range(ncols),key=lambda i:heights[i]);x=gx+60+col*500;y=heights[col]
   positions[t]=(x,y,400,cards[t].height,color)
   heights[col]+=cards[t].height+90
  bottom=max(heights)-30
  group_boxes.append((gx,gy,width,bottom-gy,name,color,len(names)))
  stack[gx]=bottom
 w=max(g[0]+g[2] for g in group_boxes)+80
 h0=max(g[1]+g[3] for g in group_boxes)+120
 # Every FK is enumerated independently of any shared or overlapping line route.
 refs=data['relationships'];nrows=math.ceil(len(refs)/3);footer_h=190+nrows*39
 im=Image.new('RGB',(w,h0+footer_h+90),'#f8fafc');d=ImageDraw.Draw(im)
 d.rounded_rectangle((35,35,w-35,260),radius=24,fill='#142b47')
 title='OLTP — 33 bảng nghiệp vụ' if kind=='oltp' else 'DW — 3 fact · 14 dimension · 2 bridge'
 d.text((80,63),'E-COMMERCE  /  DATABASE SCHEMA',font=font(25,True),fill='#b7ceee')
 d.text((80,108),title,font=font(49,True),fill='white')
 d.text((80,185),'Thẻ bảng xuất trực tiếp từ drawSQL · Ghép nhóm và vẽ lại FK từ DDL · Không lặp bảng',font=font(25),fill='#dce8f8')
 d.text((80,223),f'{len(data["tables"])} tables   •   {sum(len(t["columns"]) for t in data["tables"].values())} columns   •   {len(refs)} physical FKs   •   PK / FK / null giữ theo nguồn',font=font(22),fill='#b7ceee')
 for x,y,gw,gh,name,color,n in group_boxes:
  d.rounded_rectangle((x,y,x+gw,y+gh),radius=20,fill=pale(color),outline=color,width=3)
  d.rounded_rectangle((x,y,x+gw,y+73),radius=18,fill=color)
  d.rectangle((x,y+40,x+gw,y+73),fill=color)
  label=name.replace('_',' & ')
  d.text((x+25,y+20),f'{label}  ·  {n}',font=font(25,True),fill='white')
 # FKs are behind native table cards. Labels #NN at the child field identify
 # overlapping routes unambiguously; a complete FK register appears below.
 for i,r in enumerate(refs,1):
  x,y,cw,ch,c=positions[r['from']];tx,ty,tw,th,_=positions[r['to']]
  cols=[q['name'] for q in data['tables'][r['from']]['columns']]
  tcols=[q['name'] for q in data['tables'][r['to']]['columns']]
  sy=y+(47+15+cols.index(r['column'])*30)*1.25
  ey=ty+(47+15+tcols.index(r['target'])*30)*1.25
  if x==tx:
   sx=x;ex=tx;mid=x-22-(i%5)*7;pts=[(sx,sy),(mid,sy),(mid,ey),(ex,ey)]
  else:
   right=tx>x;sx=x+cw if right else x;ex=tx if right else tx+tw
   mid=(sx+ex)/2+(i%5-2)*9
   pts=[(sx,sy),(mid,sy),(mid,ey),(ex,ey)]
  d.line(pts,fill='#9aa6b8',width=2)
  d.ellipse((ex-5,ey-5,ex+5,ey+5),fill=c)
 # Preserve exact DrawSQL cards, including PK/index icons and null markers.
 for t,(x,y,cw,ch,c) in positions.items():
  im.paste(cards[t],(x,y));d.rectangle((x-2,y-2,x+cw+2,y+ch+2),outline='#ced6df',width=2)
  d.rectangle((x,y,x+cw,y+4),fill=c)
 for i,r in enumerate(refs,1):
  x,y,cw,ch,c=positions[r['from']];tx=positions[r['to']][0]
  index=[q['name'] for q in data['tables'][r['from']]['columns']].index(r['column'])
  sy=y+(47+15+index*30)*1.25
  sx=x+cw+7 if tx>x else x-47
  d.rounded_rectangle((sx,sy-11,sx+40,sy+12),radius=5,fill='white',outline='#cbd5e1')
  d.text((sx+4,sy-9),f'{i:02}',font=font(15,True),fill=c)
 d.rounded_rectangle((60,h0,w-60,h0+footer_h),radius=20,fill='white',outline='#cbd5e1',width=2)
 d.text((90,h0+25),'DANH SÁCH FK VẬT LÝ  ·  #NN tại cột con → bảng cha',font=font(28,True),fill='#142b47')
 cell=(w-180)//3
 for i,r in enumerate(refs):
  col=i//nrows;row=i%nrows
  txt=f'{i+1:02}  {r["from"]}.{r["column"]} → {r["to"]}.{r["target"]}'
  size=18
  while d.textlength(txt,font=font(size))>cell-30:size-=1
  d.text((90+col*cell,h0+85+row*39),txt,font=font(size),fill='#475569')
 d.text((90,h0+footer_h-55),'drawSQL · Nguồn: OLTP snapshot 09/11/2026; DW: dw/sql/30_dw. Chỉ nối REFERENCES có thật; không tự thêm FK SKU / order_code.',font=font(21),fill='#64748b')
 name='OLTP_FULL_33_TABLES' if kind=='oltp' else 'DW_FULL_19_TABLES'
 im.save(P/(name+'.png'),optimize=True)
 im.save(P/(name+'.jpg'),quality=95,subsampling=0)
 thumb=im.copy();thumb.thumbnail((1800,1800));thumb.save(P/(name+'_preview.jpg'),quality=92)
 print(name,im.size)
 # Verify every source field is represented by exactly one retained table card.
 (P/(name+'_inventory.json')).write_text(json.dumps({'table_count':len(cards),'tables':sorted(cards),'column_count':sum(len(t['columns']) for t in data['tables'].values()),'fk_count':len(refs),'method':'Native DrawSQL JPG table crops + grouped composite + DDL FK routing'},indent=2))
if __name__=='__main__':
 compose('oltp');compose('dw')
