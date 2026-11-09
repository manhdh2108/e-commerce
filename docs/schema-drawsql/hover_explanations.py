"""Shared hover explanations for the self-contained OLTP and DW viewers."""
import json

OLTP_GROUPS = [
'Quản lý danh mục, sản phẩm và người bán: xác định sàn bán gì, do ai bán, thuộc ngành hàng nào. Đây là dữ liệu nền cho đặt hàng, khuyến mãi và phân tích sản phẩm/người bán trong DW.',
'Ghi nhận khách hàng và toàn bộ nghiệp vụ mua hàng: từ checkout, tách đơn theo người bán, dòng hàng, thanh toán tới trả hàng, hoàn tiền và đánh giá. Cung cấp dữ liệu nguồn cho fact bán hàng trong DW.',
'Quản lý hàng tại kho và quá trình giao nhận: tồn hiện tại, biến động, số dư cuối ngày, vận đơn và các lần giao. Dữ liệu cuối ngày và biến động là nguồn của fact tồn kho DW.',
'Quản lý chiến dịch quảng cáo, chi phí, voucher và lượt sử dụng. Kết nối hoạt động tiếp thị với đơn hàng; cung cấp dữ liệu cho fact quảng cáo và dimension/bridge khuyến mãi trong DW.',
'Ghi nhận hành vi truy cập: phiên, tìm kiếm/xem sản phẩm và giỏ hàng. Hỗ trợ theo dõi hành trình đến đơn hàng; fact hành vi khách hàng thuộc lộ trình mở rộng DW.',
'Quản lý chính sách hoa hồng và đối soát tiền cho người bán: tổng kỳ chi trả và chi tiết dòng hàng. Fact bán hàng hiện có measure hoa hồng; fact đối soát seller riêng thuộc lộ trình mở rộng DW.'
]
OLTP_TABLES = {
'categories':'Cây ngành hàng: tên, cấp và danh mục cha. Sản phẩm tham chiếu danh mục để phân loại; chính sách hoa hồng cũng xác định theo danh mục.',
'sellers':'Hồ sơ người bán và cửa hàng, gồm hạng, địa bàn và trạng thái hoạt động. Sản phẩm, đơn hàng và kỳ chi trả gắn với người bán; thay đổi thuộc tính là nguồn theo dõi lịch sử Seller trong DW.',
'products':'Danh mục sản phẩm bán trên sàn: mã sản phẩm/SKU, giá, thương hiệu, ngành hàng, người bán và trạng thái. Được tham chiếu từ dòng đơn, giỏ hàng và hành vi; dữ liệu nền cho Dim_Product.',
'customers':'Hồ sơ khách hàng đăng ký, thông tin nhận diện, địa bàn và hạng thành viên. Đơn hàng có thể không có customer_id khi khách vãng lai. DW dùng dữ liệu này cho Customer và hồ sơ mini-dimension.',
'customer_addresses':'Địa chỉ nhận hàng của khách, người nhận, số liên hệ và cờ mặc định. Đơn hàng tham chiếu địa chỉ giao hàng được chọn.',
'channels':'Danh mục kênh bán/truy cập như Web, App, Livestream. Phiên truy cập và đơn hàng tham chiếu kênh; DW chuẩn hóa biến thể mã kênh trước khi phân tích.',
'payment_methods':'Danh mục phương thức và nhóm thanh toán. Mỗi giao dịch thanh toán tham chiếu phương thức sử dụng.',
'checkouts':'Một lần thực hiện checkout, gắn phiên và khách hàng. Liên kết các đơn phát sinh trong cùng lần mua, kể cả khi tách theo nhiều người bán.',
'checkout_lines':'Bảng nối chi tiết checkout với mục giỏ hàng và dòng đơn được tạo. Giúp truy vết một lựa chọn trong giỏ đã chuyển thành dòng đơn nào.',
'orders':'Đầu đơn theo người bán: khách, kênh, chiến dịch, trạng thái, các tổng tiền và mốc thời gian. checkout_id liên kết lần mua chung. Đơn Completed là nguồn lấy các dòng hàng cho fact bán hàng DW.',
'order_items':'Từng dòng sản phẩm trong đơn: số lượng, giá, giảm giá, tiền thuần, trạng thái và thông tin hoa hồng tại giao dịch. Là nguồn atomic chính cho Fact_Order_Item.',
'order_item_promotions':'Chi tiết voucher áp vào từng dòng hàng và số tiền giảm thực tế, kèm bên tài trợ. DW dùng để lập nhóm voucher và tính trọng số phân bổ qua bridge.',
'payments':'Các giao dịch thanh toán của đơn: phương thức, trạng thái, số tiền và thời điểm. Một đơn có thể có các bản ghi thanh toán; cần xét trạng thái thay vì cộng mọi lần thử.',
'refunds':'Yêu cầu/giao dịch hoàn tiền, gắn đơn và có thể gắn yêu cầu trả hàng. Theo dõi số tiền, lý do, trạng thái và mốc hoàn tất; tách biệt nghiệp vụ trả hàng vật lý.',
'returns':'Yêu cầu trả một số lượng của dòng hàng: lý do, quyết định, trạng thái và các mốc duyệt/nhận/hoàn tiền. warehouse_id xác định kho nhận trả khi có.',
'product_reviews':'Đánh giá sau mua gắn dòng đơn, sản phẩm và khách: điểm, bình luận và thời gian. Lưu phản hồi của khách về sản phẩm đã mua.',
'warehouses':'Danh mục kho vật lý, mã, tên và địa chỉ. Là điểm tham chiếu của tồn kho, vận chuyển và nhận trả hàng.',
'carriers':'Danh mục đơn vị vận chuyển. Vận đơn tham chiếu để xác định đơn vị phụ trách giao nhận.',
'inventory_levels':'Trạng thái tồn hiện tại theo kho và SKU: quantity_on_hand là tồn vật lý, quantity_reserved là phần đang giữ; lượng có thể bán = on_hand − reserved. Thay đổi khi giữ/nhả hàng hoặc phát sinh biến động; không phải lịch sử cuối ngày.',
'inventory_movements':'Nhật ký biến động tồn theo kho–SKU, gồm loại biến động, lượng tăng/giảm, mã tham chiếu và thời điểm. Giải thích vì sao tồn thay đổi; DW tổng hợp nhập/bán/trả/điều chỉnh từ nguồn này.',
'inventory_daily_balance':'Số dư tồn cuối ngày theo ngày–kho–SKU, gồm tồn và lượng giữ. Đây là nguồn snapshot của Fact_Inventory_Snapshot; SKU phải được ánh xạ sang product_id khi nạp DW.',
'shipments':'Vận đơn theo order_code: kho xuất, hãng vận chuyển, tracking, trạng thái, chi phí và các mốc giao nhận. order_code là liên hệ nghiệp vụ với orders; không tự suy diễn thành FK nếu DDL không khai báo.',
'delivery_attempts':'Từng lần thử giao của một vận đơn: thứ tự lần giao, kết quả và thời điểm. Giúp phân biệt giao lần đầu thành công với phải giao lại.',
'marketing_campaigns':'Định nghĩa chiến dịch: mã/tên, loại, kênh mục tiêu, ngân sách và thời hạn. Phiên, đơn và nhật ký quảng cáo có thể gắn chiến dịch; DW dùng Dim_Campaign.',
'ad_spend_logs':'Số liệu quảng cáo theo chiến dịch, mã kênh và ngày: chi phí, hiển thị, lượt nhấp. DW giữ chi tiết ngày ở staging rồi tổng hợp tháng vào Fact_Ad_Spend.',
'promotions':'Định nghĩa voucher: mã, loại, cấp áp dụng, người bán/sản phẩm, điều kiện, mức giảm, giới hạn lượt và thời hạn. Phân biệt cấu hình ưu đãi với lần áp dụng thực tế.',
'promotion_usages':'Theo dõi lượt dùng voucher trên đơn/khách, số tiền giảm, trạng thái và thời điểm giải phóng. Hỗ trợ quản lý giới hạn sử dụng; khác với phân bổ giảm giá từng dòng hàng.',
'sessions':'Phiên truy cập của khách hoặc khách vãng lai: kênh, chiến dịch, nguồn truy cập, thiết bị và thời gian bắt đầu/kết thúc. Kết nối hành vi với checkout/đơn.',
'page_events':'Các sự kiện trong phiên như tìm kiếm, xem sản phẩm hoặc sự kiện gắn đơn: loại, thời gian, từ khóa và đối tượng liên quan. Cung cấp chi tiết hành vi theo thời điểm.',
'cart_items':'Mục giỏ hàng theo phiên/khách và sản phẩm: số lượng, trạng thái, thời điểm thêm/đóng. checkout_lines truy vết mục giỏ nào đã chuyển sang dòng đơn.',
'seller_commission_rates':'Chính sách tỷ lệ hoa hồng theo danh mục và hạng người bán trong khoảng hiệu lực. Dòng đơn giữ thông tin hoa hồng áp dụng tại giao dịch để phục vụ tính tiền và đối soát.',
'seller_payouts':'Tổng đối soát/chi trả của một người bán trong kỳ: doanh số, hoàn tiền, hoa hồng, số tiền chi và trạng thái thanh toán.',
'seller_payout_items':'Chi tiết các dòng đơn thuộc một kỳ chi trả, gồm tiền hàng, hoàn, hoa hồng và tiền ròng. Trong FinanceWorkflow, gross_amount cộng lại phần voucher do sàn tài trợ vào net_amount; hoàn tính theo tỷ lệ lượng trả, hoa hồng tính trên phần còn lại. Không đồng nhất với measure seller_net_amount trong DW.'
}
SNAPSHOT_ONLY_TABLES = {'checkouts', 'checkout_lines', 'delivery_attempts', 'promotion_usages', 'refunds', 'seller_payout_items'}
for name in SNAPSHOT_ONLY_TABLES:
    OLTP_TABLES[name] += ' Bảng có trong snapshot OLTP dùng vẽ; business_schema.json của checkout mã nguồn hiện tại chưa định nghĩa bảng này, nên mô tả không xác nhận luồng này đang chạy được từ checkout đó.'

DW_GROUPS = [
'Ba fact của ba quy trình: bán hàng ở grain dòng đơn hoàn tất, tồn kho ở grain sản phẩm–kho–ngày, quảng cáo ở grain chiến dịch–kênh–tháng. Đây là nơi lưu measure để phân tích; không JOIN trực tiếp fact với fact.',
'Dimension thời gian và kênh dùng chung. Date có hai vai trò trong bán hàng (đặt/hoàn tất), Month phục vụ quảng cáo; Channel chuẩn hóa kênh để so sánh doanh thu và chi phí ở cùng grain.',
'Dimension sản phẩm có lịch sử SCD2 và cây danh mục cùng closure bridge. Giúp phân tích theo phiên bản sản phẩm, danh mục lá hoặc cả cây con. Cấu trúc/tên cây danh mục là SCD1 hiện tại, không lưu lịch sử thay đổi cây.',
'Lưu người bán theo phiên bản SCD2 và bảng hạng gần nhất SCD3. Cho phép so sánh hạng/vùng lúc bán với hiện tại, đồng thời xem lần đổi hạng gần nhất. Hai bảng liên hệ logic bằng seller_id.',
'Dimension khách hàng lưu lịch sử địa bàn; mini-dimension tách các tổ hợp hạng–chi tiêu–tần suất. Fact tham chiếu riêng hai dimension để phân tích khách theo ngữ cảnh giao dịch.',
'Chiến dịch dùng chung giữa bán hàng và quảng cáo; voucher qua nhóm và bridge nhiều–nhiều. Muốn tránh cộng lặp tiền khi JOIN bridge phải nhân doanh thu/giảm giá với weighting_factor; chỉ JOIN rồi SUM nguyên tiền vẫn gây lặp.',
'Dimension danh mục nhỏ cho kho và phương thức thanh toán. Warehouse mô tả nơi giữ hàng cho fact tồn kho; Payment method mô tả cách thanh toán cho fact bán hàng.'
]

def enhance_hover(html, data, kind):
    groups = DW_GROUPS if kind == 'dw' else OLTP_GROUPS
    notes = data['notes'] if kind == 'dw' else OLTP_TABLES
    assert set(notes) == set(data['tables']), 'Every table must have an explanation'
    assert len(groups) == len(data['groups'])
    if 'id="info"' not in html:
        panel = '<aside id="info" aria-label="Giải thích sơ đồ"><button id="close-info" aria-label="Đóng thông tin">×</button><small id="info-kind">HƯỚNG DẪN</small><h2>Khám phá sơ đồ</h2><p>Rê chuột vào một nhóm hoặc bảng để xem ý nghĩa tại đây. Khung giữ nội dung gần nhất để bạn có thể đọc và cuộn.</p></aside>'
        html = html.replace('</main>', panel+'</main>', 1)
    else:
        html = html.replace('<h2>Galaxy schema · DW hiện tại</h2>', '<small id="info-kind">HƯỚNG DẪN</small><h2>Galaxy schema · DW hiện tại</h2>')
    css = '''<style>
#info{position:absolute;right:18px;bottom:18px;width:min(440px,calc(100% - 36px));max-height:40%;overflow:auto;padding:18px 20px;background:#fffffff5;color:#19324b;border:1px solid #cbd5e1;border-top:4px solid var(--info-color,#7c3aed);border-radius:14px;box-shadow:0 10px 35px #142b4726;z-index:3;line-height:1.65;cursor:auto;user-select:text}#info[hidden]{display:none}#info h2{font-size:16px;margin:4px 22px 9px 0;overflow-wrap:anywhere}#info p{margin:0;font-size:13px}#info small{font-size:10px;font-weight:750;letter-spacing:1px;color:var(--info-color,#7c3aed)}#info button{position:absolute;right:7px;top:7px;padding:2px 8px;border:0;background:transparent}.table-head:hover,.group-head:hover{filter:brightness(1.08)}@media(max-width:700px){#info{right:10px;bottom:10px;max-height:33%;padding:12px 16px}}
</style>'''
    payload = json.dumps({'groups':groups,'tables':notes},ensure_ascii=False).replace('</','<\\/')
    js = '''<script id="hover-data" type="application/json">__HOVER__</script><script>
(()=>{'use strict';const H=JSON.parse(document.getElementById('hover-data').textContent),D=JSON.parse(document.getElementById('data').textContent),panel=document.getElementById('info'),title=panel.querySelector('h2'),body=panel.querySelector('p'),kind=panel.querySelector('small');let current='';
function show(type,key){const id=type+':'+key;if(id===current&&!panel.hidden)return;current=id;panel.hidden=false;let index=type==='group'?Number(key):D.groups.findIndex(g=>g[2].includes(key));let color=D.groups[index][1];panel.style.setProperty('--info-color',color);kind.textContent=type==='group'?'NHÓM CHỨC NĂNG · '+D.groups[index][2].length+' BẢNG':'BẢNG DỮ LIỆU';title.textContent=type==='group'?document.querySelector('#systems').children[index].textContent:key;body.textContent=type==='group'?H.groups[index]:H.tables[key]}
document.getElementById('schema').addEventListener('pointerover',e=>{const table=e.target.closest('[data-table]');if(table){show('table',table.dataset.table);return}const group=e.target.closest('[data-group]');if(group)show('group',group.dataset.group)});
Array.from(document.querySelector('#systems').children).forEach((button,i)=>{button.addEventListener('pointerenter',()=>show('group',i));button.addEventListener('focus',()=>show('group',i));button.addEventListener('click',()=>show('group',i))});
panel.addEventListener('pointerdown',e=>e.stopPropagation());panel.addEventListener('wheel',e=>e.stopPropagation());document.getElementById('close-info').onclick=()=>{panel.hidden=true;current=''};
})();</script>'''.replace('__HOVER__',payload)
    return html.replace('</html>',css+js+'</html>')
