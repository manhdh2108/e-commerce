"""Tái tạo hai SVG; dùng Chrome headless để xuất PNG cùng kích thước."""
from pathlib import Path
from html import escape
import subprocess

OUT = Path(__file__).resolve().parent
C = {'catalog':'#7c3aed','orders':'#2563eb','warehouse':'#059669','marketing':'#e07816','analytics':'#0891b2','finance':'#db2777','dw':'#334155'}
class Canvas:
    def __init__(self,w,h):
        self.w,self.h=w,h
        self.s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">', '<title>Bản đồ tác động hệ thống thương mại điện tử</title>', '<defs><pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#dce4ef"/></pattern><filter id="shadow" x="-15%" y="-20%" width="135%" height="150%"><feDropShadow dx="0" dy="5" stdDeviation="8" flood-color="#152d50" flood-opacity=".07"/></filter>']
        for k,c in C.items(): self.s.append(f'<marker id="arr-{k}" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9Z" fill="{c}"/></marker>')
        self.s+=['</defs>',f'<rect width="{w}" height="{h}" fill="#f5f8fc"/>',f'<rect width="{w}" height="{h}" fill="url(#grid)"/>']
    def rect(self,x,y,w,h,fill='white',stroke='none',r=18,extra=''):
        self.s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" {extra}/>')
    def text(self,x,y,t,size=18,color='#475569',weight=400):
        self.s.append(f'<text x="{x}" y="{y}" font-family="Lato, DejaVu Sans, sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(t)}</text>')
    def header(self,n,title,subtitle):
        self.text(60,48,f'E-COMMERCE  /  SYSTEM IMPACT ATLAS  /  {n}',15,'#64748b',700)
        self.text(60,105,title,38,'#10243b',900)
        self.text(60,144,subtitle,19)
        self.rect(60,170,self.w-120,52,'#fff7ed','#fed7aa',12)
        self.text(80,202,'ĐỌC ĐÚNG PHẠM VI: source mock còn conflict; sơ đồ là đối chiếu logic, không phải xác nhận runtime.',18,'#9a4c11',700)
    def card(self,x,y,w,h,k,num,title,lines,tag=None):
        c=C[k]; self.rect(x,y,w,h,'white','#dce5f1',18,'filter="url(#shadow)"')
        self.rect(x,y,7,h,c,r=3)
        self.rect(x+22,y+22,40,34,c,r=10); self.text(x+31,y+46,num,16,'white',900)
        self.text(x+76,y+47,title,23,'#132b46',800)
        for i,t in enumerate(lines): self.text(x+24,y+84+i*27,t,18)
        if tag: self.text(x+24,y+h-20,tag,14,c,700)
    def edge(self,points,k='orders',label=None,dashed=False,lp=None):
        d='M '+' L '.join(f'{x},{y}' for x,y in points)
        self.s.append(f'<path d="{d}" fill="none" stroke="{C[k]}" stroke-width="2.7" stroke-linejoin="round" stroke-linecap="round" marker-end="url(#arr-{k})" '+('stroke-dasharray="8 7"' if dashed else '')+'/>')
        if label:
            x,y=lp or points[len(points)//2]; w=len(label)*9+24
            self.rect(x-w/2,y-18,w,28,'#f5f8fc',r=7); self.text(x-w/2+12,y+2,label,15,C[k],700)
    def footer(self,y):
        self.edge([(70,y),(130,y)],'orders'); self.text(145,y+5,'Nét liền: quan hệ có trong code nền / ETL',17)
        self.edge([(700,y),(760,y)],'finance',dashed=True); self.text(775,y+5,'Nét đứt: thiết kế / chưa xác minh nối đầy đủ',17)
        self.text(60,y+45,'09/11/2026 · Checkout 1cb38fd · Nguồn ưu tiên: MOCK_SYSTEM_RULES (Rule 01–08)',15,'#64748b')
    def save(self,name):
        p=OUT/(name+'.svg'); p.write_text('\n'.join(self.s+['</svg>']),encoding='utf-8')
        cmd=['google-chrome','--headless','--no-sandbox','--disable-gpu','--hide-scrollbars','--no-first-run','--no-default-browser-check',f'--screenshot={OUT/(name+".png")}',f'--window-size={self.w},{self.h}',f'file://{p}']
        subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=45)

def overview():
    s=Canvas(1800,1530)
    s.header('01','Một thay đổi đi xa đến đâu?','Sáu miền nghiệp vụ • điều kiện bán → giao dịch → hàng & tiền → dữ liệu phân tích')
    s.rect(60,250,1680,115,'#eaf0f9','#d8e3f3')
    s.text(85,284,'NGUỒN & ĐIỀU KHIỂN',15,'#52647e',800)
    s.text(85,319,'Tiki → SQLite → Đồng bộ chủ động → Chỉ thêm catalog mới',23,'#233b5b',800)
    s.text(85,345,'Rule 01–02: không tự tạo tồn/đơn  •  Rule 07: config → preview → job snapshot  •  Rule 04–05: quota hoặc theo đầu vào',17)
    s.edge([(300,365),(300,420)],'catalog','sync',lp=(300,400))
    s.card(60,420,480,225,'catalog','01','Catalog & Seller', ['Sản phẩm · Danh mục · Người bán','Đổi trạng thái → đổi tập được bán','Đổi hạng/tỉnh → nguồn cho SCD'], 'SEL / CAT / MGR • chỉ số Tiki là snapshot')
    s.card(660,420,480,225,'orders','02','Khách hàng & Đơn hàng',['Checkout → giữ hàng → thanh toán','Xác nhận khi COD / đã trả trước','Hủy hợp lệ → giải phóng hàng giữ'], 'GST / CUS / PAY / ORD / SYS')
    s.card(1260,420,480,225,'warehouse','03','Kho vận',['Tồn khả dụng quyết định nhận đơn','Pickup → trừ tồn, ghi movement Sale','Delivered → Completed; COD thu riêng'], 'WH / DSP / CAR / AUT-WH')
    s.edge([(540,505),(660,505)],'catalog','được bán',lp=(600,491))
    s.edge([(1140,505),(1260,505)],'orders','giữ / xuất',lp=(1200,491))
    s.edge([(1260,590),(1140,590)],'warehouse','giao / COD',lp=(1200,620))
    s.card(60,840,480,225,'marketing','04','Marketing',['Campaign · Voucher · Báo cáo ads','Ngân sách không tự sinh đơn/traffic','Voucher cần luồng áp dụng thực'], 'MKT / SHOP-MKT / ADS')
    s.card(660,840,480,225,'analytics','05','Web analytics',['Phiên → xem hàng → giỏ → checkout','Begin_checkout chưa phải đơn thật','Purchase / đóng giỏ cần nối kết quả'], 'GST-WEB / CUS-WEB / AUT-WEB / EVT')
    s.card(1260,840,480,225,'finance','06','Tài chính',['Policy · Nghĩa vụ · Đối soát · Chi trả','Đọc đơn, tiền thu, voucher, hoàn hàng','Không hồi tố chứng từ đã chốt'], 'FIN / AUT-FIN • cần xác minh tích hợp')
    s.edge([(300,840),(300,735),(790,735),(790,645)],'marketing','voucher / tiền giảm',True,(515,735))
    s.edge([(540,950),(660,950)],'marketing','campaign',True,(600,932))
    s.edge([(960,840),(960,645)],'analytics','phiên ↔ kết quả mua',True,(960,762))
    s.edge([(1100,645),(1100,695),(1500,695),(1500,840)],'finance','đơn + tiền thu + nghĩa vụ',True,(1310,695))
    s.edge([(1740,560),(1770,560),(1770,950),(1740,950)],'finance',dashed=True)
    s.rect(60,1130,1680,145,'#142b47')
    s.text(90,1167,'LỚP PHÂN TÍCH — CÓ ĐỘ TRỄ BATCH',15,'#a5c2e6',800)
    s.text(90,1206,'OLTP + SQLite → raw → stg / DQ → DW / SCD / 3 fact → mart → dashboard',27,'white',800)
    s.text(90,1243,'Doanh thu: ngày hoàn tất  •  Tồn: cuối kỳ / bình quân  •  Ads: tháng–kênh  •  Chỉ refresh sau batch SUCCESS',18,'#d1def0')
    s.edge([(300,1065),(300,1130)],'marketing','ads',lp=(300,1104))
    s.edge([(1500,1065),(1500,1130)],'dw','phần nguồn ETL sử dụng',lp=(1500,1104))
    s.edge([(70,645),(35,645),(35,1200),(60,1200)],'dw')
    s.rect(60,1305,1680,80,'white','#dce5f1',12)
    s.text(85,1336,'ĐIỂM CHỐT',15,'#334155',900)
    s.text(85,1365,'Thay đổi dữ liệu chỉ mở điều kiện cho bước sau. Có luồng thiết kế ≠ đã nối đầy đủ. Dashboard không tự điều khiển ngược OLTP.',18)
    s.footer(1430); s.save('01_tong_quan_tac_dong')

def detailed():
    s=Canvas(1800,2070)
    s.header('02','Tương tác chi tiết theo vòng đời nghiệp vụ','Đọc từ trên xuống • Mã # đối chiếu sổ luồng trong bản tổng hợp • Các đường thể hiện luồng logic')
    for x,t,k in [(60,'A / CATALOG & NHU CẦU','catalog'),(660,'B / ĐƠN HÀNG & THANH TOÁN','orders'),(1260,'C / KHO VẬN & NGHĨA VỤ','warehouse')]:
        s.rect(x,250,480,45,C[k],r=12); s.text(x+20,280,t,17,'white',800)
    s.card(60,330,480,160,'catalog','02','Catalog sẵn sàng',['Sync thêm mới · seller/product hợp lệ','Tạm dừng / khóa → chặn bán mới'],'SQLite độc lập • chưa có tồn tự động')
    s.card(660,330,480,160,'orders','05','Checkout + giữ hàng',['Đơn Pending · 1 SKU / 1 shop (nền)','Dòng giá chốt · địa chỉ · metadata'],'Điều kiện: active, giá > 0, available ≥ q')
    s.card(1260,330,480,160,'warehouse','03','Tồn kho & nhập hàng',['available = on_hand − reserved','Checkout: reserved += q'],'Bootstrap / WH-01 là bước chạy riêng')
    s.edge([(540,390),(660,390)],'catalog','#04',lp=(600,377))
    s.edge([(1140,390),(1260,390)],'orders','#05',lp=(1200,377))
    s.card(60,580,480,160,'marketing','14','Chiến dịch & voucher',['Campaign → ad_spend_logs → DW','Voucher mới chỉ là định nghĩa'],'Tạo ads không tự làm traffic/đơn tăng')
    s.card(660,580,480,160,'orders','06','Thanh toán trả trước',['Pending → Success hoặc Failed','Retry / quá hạn tùy đầu vào hợp lệ'],'COD đi theo điều kiện xác nhận riêng')
    s.card(1260,580,480,160,'warehouse','09','Vận đơn Created',['Đơn Processing · còn giữ hàng','DSP-01 nối bằng order_code'],'Chỉ tạo khi chưa có shipment')
    s.edge([(900,490),(900,580)],'orders')
    s.edge([(540,645),(615,645),(615,460),(660,460)],'marketing','#15',True,(614,548))
    s.card(660,830,480,160,'orders','07','Xác nhận xử lý đơn',['Pending → Processing','Seller Active + (COD hoặc đã trả)'],'Thiếu điều kiện → chưa được xác nhận')
    s.edge([(900,740),(900,830)],'orders')
    s.edge([(1140,890),(1190,890),(1190,650),(1260,650)],'orders','#09',lp=(1190,789))
    s.card(1260,830,480,160,'warehouse','10','Pickup & xuất kho',['Created → Picked → In Transit','on_hand −= q; reserved −= q; Sale −q'],'CAR-01 / WH-03: không xuất hai lần')
    s.edge([(1500,740),(1500,830)],'warehouse')
    s.card(60,830,480,160,'analytics','16','Phiên, sự kiện & giỏ',['view / search / add_to_cart','begin_checkout chưa tạo đơn thật'],'Liên kết session–order còn thiếu ở nền')
    s.edge([(300,740),(300,830)],'marketing','nguồn campaign',True,(300,789))
    s.edge([(540,900),(580,900),(580,350),(660,350)],'analytics','#16',True,(580,787))
    s.card(660,1080,480,160,'orders','08','Hủy đơn hợp lệ',['Pending/Processing → Cancelled','Giải phóng reserved của chính đơn'],'Nền chặn khi có shipment / đã thu tiền')
    s.edge([(900,990),(900,1080)],'orders','nhánh hủy nếu đủ điều kiện',lp=(900,1039))
    s.card(1260,1080,480,160,'warehouse','11','Giao thành công & thu COD',['Delivered → Completed / Fulfilled','COD: ghi payment Success riêng (#12)'],'Failed: chưa khép luồng hoàn kho/tiền')
    s.edge([(1500,990),(1500,1080)],'warehouse')
    s.edge([(1260,1160),(1185,1160),(1185,1018),(1070,1018),(1070,990)],'warehouse','#11–12',lp=(1185,1054))
    s.rect(60,1080,480,160,'#ecfeff','#a5e7ef',18)
    s.text(85,1118,'ĐIỂM KHÔNG ĐƯỢC SUY DIỄN',16,'#0e7490',900)
    for i,t in enumerate(['Giỏ + đơn cùng khách chưa đủ liên kết.','Chỉ ghi purchase khi có kết quả thật.','Không lấy tổng views để suy doanh thu.']): s.text(85,1152+i*28,t,18)
    s.card(60,1360,480,170,'orders','17','Sau bán: trả / hoàn',['Requested → duyệt → nhận → refund','Kho nhận lại tùy chất lượng hàng'],'Thiết kế: số lượng, tiền, thời gian cần chốt')
    s.card(660,1360,480,170,'finance','18','Nghĩa vụ & đối soát',['Đơn đã giao + tiền thu + policy','Voucher bên tài trợ + hoàn tiền'],'Không tạo payout giả / không hồi tố Paid')
    s.card(1260,1360,480,170,'finance','18','Duyệt & chi seller',['Đối soát → duyệt → kết quả chi','Cần ledger và tích hợp schema đúng'],'Có module nâng cấp ≠ đã chạy tích hợp')
    s.edge([(1500,1240),(1500,1295),(900,1295),(900,1360)],'finance','#18',True,(1130,1295))
    s.edge([(540,1440),(660,1440)],'finance','điều chỉnh',True,(600,1420))
    s.edge([(1140,1440),(1260,1440)],'finance','nghĩa vụ hợp lệ',True,(1200,1420))
    s.edge([(1280,1240),(1280,1265),(300,1265),(300,1360)],'orders','#17',True,(510,1265))
    s.rect(60,1620,1680,200,'#142b47')
    s.text(90,1660,'#19–20 / CUỐI NGÀY & KHO DỮ LIỆU',16,'#a5c2e6',800)
    s.text(90,1703,'Chốt tồn → Validation → last_day → Extract → Transform / DQ → Load / SCD',27,'white',800)
    s.text(90,1744,'3 fact: dòng hàng hoàn tất  |  tồn SKU–kho–ngày  |  ads campaign–kênh–tháng',22,'#d5e4f8',700)
    s.text(90,1783,'Đối soát đạt → SUCCESS → refresh mart → dashboard  •  Sai load → rollback  •  Refresh lỗi → báo mart cũ',19,'#d5e4f8')
    s.edge([(900,1530),(900,1620)],'dw','dữ liệu nguồn ETL hỗ trợ',lp=(900,1580))
    s.edge([(1735,990),(1770,990),(1770,1680),(1740,1680)],'warehouse')
    s.rect(60,1850,1680,65,'white','#dce5f1',12)
    s.text(85,1889,'RULE XUYÊN SUỐT: không bù quota bằng dữ liệu giả • theo đầu vào chỉ xử lý đủ điều kiện • plan/job giữ snapshot • không tác động trùng',18,'#334155',700)
    s.footer(1960); s.save('02_chi_tiet_tuong_tac')

if __name__ == '__main__':
    overview(); detailed()
