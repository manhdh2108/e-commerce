"""Build the portable DW viewer. Standard library only; no network dependencies."""
from pathlib import Path
import ast
import json
import re

P = Path(__file__).resolve().parent
# Reuse the OLTP viewer's interaction engine without executing its builder.
module = ast.parse((P / 'build_single_view.py').read_text())
template = next(ast.literal_eval(n.value) for n in module.body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'template' for t in n.targets))
data = json.loads((P / 'dw_metadata.json').read_text())
assert len(data['tables']) == 19
assert sum(len(t['columns']) for t in data['tables'].values()) == 200
assert len(data['relationships']) == 26
# PK columns are NOT NULL even when the DDL declares a composite PK separately.
for t in data['tables'].values():
    for c in t['columns']:
        if c['name'] in t['pk']:
            c['nullable'] = False
notes = {
'fact_order_item': 'TRANSACTION · 1 dòng sản phẩm trong đơn Completed; item_status Fulfilled/Returned. date_key là ngày hoàn tất; order_date_key là ngày đặt. Khóa nghiệp vụ: source_system + order_id + line_number; PK thêm date_key để partition tháng. Tra Product/Seller/Customer theo ngày hoàn tất trong [valid_from, valid_to). order_code là degenerate dimension. gross = quantity × unit_price; net = gross − discount. is_returned không thay thế một Fact_Return. net_revenue chưa phải doanh thu sau hoàn tiền.',
'fact_inventory_snapshot': 'PERIODIC SNAPSHOT THƯA · 1 sản phẩm × 1 kho × cuối 1 ngày. PK: date_key + product_key + warehouse_key. Không có dòng = không kinh doanh, khác với tồn 0 = hết hàng. available = on_hand − reserved. Tồn và giá trị tồn là semi-additive: không SUM qua ngày/tháng. Product được tra phiên bản tại balance_date. Partition theo tháng.',
'fact_ad_spend': 'PERIODIC THÁNG · 1 tháng × 1 chiến dịch × 1 kênh. PK: month_key + campaign_key + channel_key. Nguồn có grain ngày tại stg.ad_spend_daily; fact chủ đích tổng hợp tháng và upsert tháng đang mở. impressions ≥ clicks; active_days 1–31. CTR/CPC tính lại từ tổng.',
'dim_date': 'SCD0 · 1 ngày, date_key dạng YYYYMMDD; lịch 2025–2027. Role-playing trong bán hàng: date_key = hoàn tất, order_date_key = đặt. Trong tồn kho: ngày snapshot. month_key có FK đến dim_month. Ngày không sử dụng khóa đặc biệt −1/0.',
'dim_month': 'SCD0 · 1 tháng, month_key dạng YYYYMM; lịch 2025–2027. Dimension thời gian trực tiếp của Fact_Ad_Spend; dùng chung với Dim_Date qua month_key. Không nối fact quảng cáo vào grain ngày.',
'dim_product': 'SCD2: list_price, category_key, is_active, unit_cost_est; kết hợp SCD1 cho tên/thương hiệu và các thuộc tính theo triển khai. UNIQUE(product_id, valid_from), duy nhất 1 current/product_id. seller_id là khóa tự nhiên, không có FK vật lý đến dim_seller. original_price và discount_rate bị ghi đè SCD1. Giá vốn là ước tính, không phải giá vốn thật.',
'dim_category': 'SCD1 · cây danh mục từ primary_category_path của crawler, cắt tại danh mục OLTP. category_key dùng mã Tiki. parent_category_key là FK tự tham chiếu; root_category_key không khai báo FK. Closure bridge hỗ trợ tổ tiên/hậu duệ và roll-up theo cây.',
'bridge_category_hierarchy': 'CLOSURE TABLE · 1 cặp ancestor_key × descendant_key; depth ≥ 0, gồm chính nó ở depth 0. Hai FK đều trỏ dim_category. Dựng lại theo batch. Lọc một tổ tiên để cộng cả cây con; tránh SUM qua toàn bộ tổ tiên gây lặp.',
'dim_seller': 'SCD2: tier, province, status; SCD1: tên shop/thông tin liên hệ theo load. seller_key là surrogate key của từng phiên bản; seller_id là mã nghiệp vụ. Fact giữ hạng/vùng lúc hoàn tất đơn, không tự đổi về thuộc tính hiện tại.',
'dim_seller_tier_t3': 'SCD3 · 1 seller_id, giữ current_tier, previous_tier và tier_changed_on. Là bảng riêng, không có FK vật lý đến dim_seller (seller_id bên SCD2 không duy nhất toàn bảng). Có thể tra cứu logic bằng seller_id; không dùng để thay seller_key trong fact.',
'dim_customer': 'SCD2 theo tỉnh; SCD1 cho thuộc tính nhận diện theo triển khai. customer_key là phiên bản, customer_id là mã nghiệp vụ. Khách vãng lai → −1; không tra được → 0. SĐT che và email chỉ giữ tên miền. Hạng khách chuyển sang mini-dimension.',
'dim_customer_profile': 'MINI-DIMENSION · 5 hạng × 5 nhóm chi tiêu 12 tháng × 5 nhóm tần suất = 125 tổ hợp, cộng −1/0. Fact giữ customer_profile_key trực tiếp; không có FK từ dim_customer sang bảng này. Chi tiêu/tần suất tính từ giao dịch trước ngày hoàn tất; hạng lấy trạng thái tại batch, một giới hạn đã nêu trong Blueprint.',
'dim_channel': 'SCD1 · kênh chuẩn Web / App / Livestream. stg.map_channel ánh xạ biến thể nguồn; mã lạ bị cách ly. Dùng chung cho bán hàng, quảng cáo và kênh mục tiêu của campaign.',
'dim_payment_method': 'SCD1 · phương thức và nhóm thanh toán. Payment đến muộn có thể tạm dùng khóa 0 (DQ-15) và được cập nhật ở batch sau; không tạo fact thanh toán riêng trong phạm vi hiện tại.',
'dim_warehouse': 'SCD1 · mã, tên kho, tỉnh và vùng đã chuẩn hóa. Chỉ fact tồn kho có FK vật lý đến dimension này; vận chuyển là phạm vi mở rộng.',
'dim_campaign': 'SCD1 · chiến dịch, ngân sách, khoảng chạy và target_channel_key (FK). Dùng chung bởi bán hàng và quảng cáo. Kênh mục tiêu của campaign và channel_key thực tế trong fact có vai trò riêng.',
'dim_promotion': 'SCD1 · voucher, bên tài trợ, cấp áp dụng, điều kiện và hiệu lực. seller_id là khóa tự nhiên, không phải FK vật lý. Fact bán hàng đi qua promotion_group và bridge thay vì chứa một promotion_key duy nhất.',
'dim_promotion_group': '1 nhóm = toàn bộ voucher trên một dòng hàng. group_signature duy nhất, chuẩn hóa danh sách voucher và trọng số. Khóa −1 cho không voucher; 0 cho chưa xác định. Nhóm dùng chung không lưu số tiền giảm giá.',
'bridge_promotion_group': 'BRIDGE NHIỀU–NHIỀU · PK (promotion_group_key, promotion_key). weighting_factor = applied_discount / tổng applied_discount; Σ weight = 1/nhóm (đối soát ETL). Tiền phân bổ = fact.discount_amount × weight. Không có allocated_discount trong DDL hiện tại. Nguồn thực tế chỉ 1 voucher hàng hóa/đơn nên weight hiện bằng 1.'
}
data['notes'] = notes
s = template.replace('OLTP — 33 bảng · 6 hệ thống', 'DW — Galaxy schema · 19 bảng')
s = s.replace('Schema snapshot 09/11/2026 · 282 cột · 56 khóa ngoại vật lý · Bản độc lập, không phải drawSQL', '3 fact · 14 dimension · 2 bridge · 200 cột · 26 FK vật lý · Đối chiếu Master Blueprint & DDL')
s = s.replace('Sáu hệ thống', 'Nhóm chức năng DW').replace('Sơ đồ OLTP tương tác', 'Sơ đồ DW tương tác')
s = s.replace('33 bảng OLTP chia thành đúng 6 nhóm hệ thống, có đủ cột và quan hệ FK', '19 bảng DW, có đủ 200 cột và 26 quan hệ FK vật lý')
s = s.replace('OLTP: 33 bảng thuộc 6 hệ thống', 'DW: Galaxy schema, 3 fact dùng chung dimension')
s = s.replace("const labels=['Catalog & Seller','Khách hàng & Đơn hàng','Kho vận','Marketing','Web Analytics','Tài chính'];", "const labels=['Fact nghiệp vụ','Thời gian & Kênh','Sản phẩm & Cây danh mục','Người bán & SCD3','Khách hàng & Mini-dim','Chiến dịch & Voucher','Kho & Thanh toán'];")
s = s.replace('w=370,rh=27,head=45', 'w=470,rh=29,head=45')
s = s.replace("const places=[[60,60,2],[1180,60,3],[2780,60,3],[60,null,2],[2780,null,2],[1180,null,2]],stack={};", "const places=[[1390,60,2],[60,60,2],[2720,60,2],[60,null,2],[60,null,2],[2720,null,2],[1390,null,2]],stack={};")
s = s.replace("let nam=text(row,49,y+19,c.name,14,pk?600:400);", "let nam=text(row,49,y+19,c.name,14,pk?600:400);")
s = s.replace("pkText,11,400", "pkText,11,400")
s = s.replace("g.node=n;let btn", "g.node=n;let btn")
s = s.replace("m.node=n}", "h.addEventListener('click',()=>{select(m.name);showTable(m.name)});m.node=n}")
s = s.replace("function select(name,col){", "function select(name,col){showTable(name); ")
s = s.replace("33 bảng · 6 hệ thống · 56 FK vật lý", "19 bảng · 7 nhóm chức năng · 26 FK vật lý · Mũi tên: bảng tham chiếu → bảng được tham chiếu")
s = s.replace('<button id="clear">Bỏ chọn</button>', '<button id="clear">Bỏ chọn</button><button id="guide">Thiết kế & Quy tắc</button>')
s = s.replace('<nav aria-label=', '<nav aria-label=',1)
s = s.replace('<span>PK: khóa chính · FK: khóa ngoại · ?: nullable</span>', '<span>PK · FK → đích tham chiếu · ?: nullable</span>')
s = s.replace('</style>', '''
#info{position:absolute;right:18px;bottom:18px;width:min(460px,calc(100% - 36px));max-height:45%;overflow:auto;padding:18px 20px;background:#ffffffed;border:1px solid #cbd5e1;border-top:4px solid #7c3aed;border-radius:12px;box-shadow:0 10px 35px #142b4720;z-index:3;line-height:1.65}#info h2{font-size:16px;margin:0 25px 8px 0}#info p{margin:0}#info button{position:absolute;right:6px;top:6px;padding:2px 8px;border:0;background:transparent}#info[hidden]{display:none}dialog{border:0;border-radius:18px;padding:28px;max-width:960px;width:92vw;max-height:85dvh;color:#19324b;line-height:1.7;box-shadow:0 25px 100px #0005}dialog::backdrop{background:#0b213bb0}dialog h2{margin-top:0}dialog h3{color:#6d28d9;margin-bottom:5px}dialog li{margin-bottom:6px}dialog .close{float:right}dialog code{background:#edf2f8;border-radius:4px;padding:2px 4px}footer #status{white-space:nowrap;overflow:hidden;text-overflow:ellipsis} .table-head:hover{filter:brightness(1.08)}
</style>''')
s = s.replace('</main>', '''<aside id="info"><button id="close-info" aria-label="Đóng thông tin">×</button><h2>Galaxy schema · DW hiện tại</h2><p>Bấm tiêu đề bảng để đọc grain, vai trò và quy tắc lịch sử. Bấm cột để tô sáng FK. Dùng các nút nhóm để xem rõ từng vùng; mở “Thiết kế & Quy tắc” để xem bus matrix và luồng ETL.</p></aside></main>''')
guide = '''<dialog id="guide-dialog"><button class="close" id="close-guide">Đóng ×</button><h2>Thiết kế DW theo Master Blueprint</h2><p><strong>19 bảng logic trong schema dw:</strong> 3 fact + 14 dimension + 2 bridge. Bảy nhóm màu là nhóm chức năng của kho, không phải bảy hệ thống nguồn. Mỗi bảng xuất hiện một lần; chỉ vẽ 26 FK khai báo trong DDL. Các partition vật lý, raw, stg, mart và audit không tính vào 19 bảng.</p>
<h3>Ba quy trình · ba grain</h3><ul><li><strong>Bán hàng:</strong> một dòng sản phẩm trong đơn hoàn tất; ngày hoàn tất là thời điểm ghi nhận. Ngày đặt là vai trò thời gian thứ hai.</li><li><strong>Tồn kho:</strong> sản phẩm × kho × cuối ngày; snapshot thưa. Không có dòng khác với tồn bằng 0.</li><li><strong>Quảng cáo:</strong> tháng × chiến dịch × kênh; chi tiết ngày giữ ở staging.</li></ul>
<h3>Dimension dùng chung · Bus matrix</h3><table style="border-collapse:collapse;width:100%"><thead><tr><th align="left">Dimension</th><th>Bán hàng</th><th>Tồn kho</th><th>Quảng cáo</th></tr></thead><tbody>
<tr><td>Date / Month</td><td align="center">Date: 2 vai trò</td><td align="center">Date</td><td align="center">Month</td></tr><tr><td>Product / Category</td><td align="center">✓</td><td align="center">✓</td><td align="center">—</td></tr><tr><td>Channel / Campaign</td><td align="center">✓</td><td align="center">—</td><td align="center">✓</td></tr><tr><td>Seller / Customer / Profile / Payment / Promotion group</td><td align="center">✓</td><td align="center">—</td><td align="center">—</td></tr><tr><td>Warehouse</td><td align="center">—</td><td align="center">✓</td><td align="center">—</td></tr></tbody></table>
<h3>Lịch sử & quan hệ đặc biệt</h3><ul><li>Product, Seller, Customer: snapshot-diff SCD2 với khoảng <code>[valid_from, valid_to)</code>, kết hợp SCD1. Đến muộn: cách ly DQ-23; không sửa hồi tố.</li><li>Seller tier SCD3 nối logic bằng <code>seller_id</code>, không có FK vật lý tới Seller SCD2. Các cột seller_id ở Product/Promotion, root_category_key và batch_id cũng không tự suy diễn thành FK.</li><li>Customer profile là mini-dimension nối trực tiếp vào fact, không nối FK sang Customer. Hạng tại batch; nhóm chi tiêu/tần suất từ các ngày trước giao dịch.</li><li>Category có self-FK và closure bridge; voucher qua group + bridge trọng số. Tổng trọng số bằng 1 do ETL đối soát, không phải CHECK đơn dòng.</li><li>−1 = không áp dụng, 0 = chưa xác định cho các dimension được DDL sinh sentinel; Date/Month dùng khóa lịch, Seller tier SCD3 không được sinh sentinel trong DDL.</li></ul>
<h3>Đọc báo cáo đúng grain</h3><p>Không JOIN trực tiếp các fact. Tổng hợp riêng từng phía rồi drill-across bằng FULL OUTER JOIN: bán hàng–quảng cáo theo <code>(month_key, channel_key)</code>; bán hàng–tồn kho theo <code>(month_key, product_id)</code>, dùng mã nghiệp vụ để gộp các phiên bản SCD2. Tồn cuối kỳ không SUM qua thời gian; AOV/CTR/CPC và distinct count phải tính lại ở grain báo cáo. Measure có hậu tố <code>_est</code> phụ thuộc giá vốn ước tính.</p>
<h3>Luồng dữ liệu & vận hành</h3><p>OLTP + crawler → <strong>raw</strong> bất biến → <strong>stg</strong> chuẩn hóa, map mã, DQ → <strong>dw</strong> dimension + fact/bridge + đối soát trong một transaction → <strong>mart</strong> (8 MV, KPI, drill-across) → dashboard. Audit lưu batch, cách ly và lineage. Chỉ đọc ngày đã chốt theo watermark; ERROR bị cách ly, WARN giữ lại. Load lỗi → rollback; mart giữ bản cũ. Refresh mart sau commit; lỗi refresh được báo stale riêng.</p>
<h3>Phạm vi hiện tại</h3><p>Fulfillment, Fact_Return, Seller_Settlement và Customer_Activity thuộc lộ trình mở rộng; chưa vẽ như bảng đã tồn tại. Hai fact lớn partition tháng 2025–2027 + default. Đây là sơ đồ cấu trúc từ mã nguồn, không truy vấn trực tiếp database và không khẳng định số batch/dòng hiện đang chạy.</p>
<p style="color:#64748b">Nguồn: docs/MASTER_BLUEPRINT.html §§2–7, 10–11; dw/sql/30_dw/301_dim_date.sql, 302_dimensions.sql, 303_facts.sql; dw/etl/load.py; dw/sql/40_mart/401_mart.sql. HTML độc lập, không cần mạng; vị trí kéo chưa lưu sau tải lại.</p></dialog>'''
s = s.replace('<script id="data"', guide+'\n<script id="data"',1)
s = s.replace("const groupModel=[],", "function showTable(name){document.getElementById('info').hidden=false;document.querySelector('#info h2').textContent=name;document.querySelector('#info p').textContent=D.notes[name]}document.getElementById('close-info').onclick=()=>document.getElementById('info').hidden=true;document.getElementById('guide').onclick=()=>document.getElementById('guide-dialog').showModal();document.getElementById('close-guide').onclick=()=>document.getElementById('guide-dialog').close();\nconst groupModel=[],")
# Space shared-column routes slightly, including both role-playing date FKs.
s = s.replace('paths){let a=', 'paths.entries()){let a=') if False else s
s = s.replace('for(let {r,path} of paths){', 'for(let [edgeIndex,{r,path}] of paths.entries()){')
s = s.replace('mid=sx-30', 'mid=sx-35-(edgeIndex%5)*11').replace('mid=(sx+ex)/2', 'mid=(sx+ex)/2+(edgeIndex%7-3)*10')
(P/'DW_19_TABLES_GALAXY.html').write_text(s.replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/')))
print(P/'DW_19_TABLES_GALAXY.html')
