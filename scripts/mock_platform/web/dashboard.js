/* Dashboard and source controls. Every mutation follows an explicit button click. */
const tableLabels={categories:'Danh mục',products:'Sản phẩm',sellers:'Người bán',customers:'Khách hàng',customer_addresses:'Địa chỉ khách',channels:'Kênh bán',payment_methods:'Phương thức thanh toán',orders:'Đơn hàng',order_items:'Chi tiết đơn',payments:'Thanh toán',returns:'Trả hàng',product_reviews:'Đánh giá',promotions:'Khuyến mãi',order_item_promotions:'Ưu đãi đã áp dụng',warehouses:'Kho',inventory_levels:'Tồn kho',inventory_movements:'Biến động kho',inventory_daily_balance:'Chốt tồn theo ngày',carriers:'Đơn vị vận chuyển',shipments:'Vận đơn',marketing_campaigns:'Chiến dịch',ad_spend_logs:'Chi phí quảng cáo',sessions:'Phiên truy cập',page_events:'Sự kiện truy cập',cart_items:'Mục giỏ hàng',seller_commission_rates:'Chính sách hoa hồng',seller_payouts:'Đối soát người bán',checkouts:'Yêu cầu checkout',checkout_lines:'Liên kết giỏ và dòng đơn',promotion_usages:'Lượt sử dụng ưu đãi',refunds:'Hoàn tiền',delivery_attempts:'Các lần giao hàng',seller_payout_items:'Chi tiết đối soát'};
const businessStatuses={Pending:'Chờ xử lý',Processing:'Đang xử lý',Completed:'Hoàn tất',Cancelled:'Đã hủy',Success:'Thành công',Failed:'Thất bại',Created:'Mới tạo',Picked:'Đã lấy hàng','In Transit':'Đang giao',Delivered:'Đã giao',Returned:'Đã nhận hàng về',Approved:'Đã duyệt',Paid:'Đã chi',Requested:'Đã yêu cầu',Received:'Đã nhận',Refunded:'Đã hoàn tiền',Converted:'Đã đặt hàng'};
function metricCards(items){return '<div class="stats">'+items.map(([label,value,hint])=>`<div class="stat"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><small>${esc(hint)}</small></div>`).join('')+'</div>'}
function statusBars(title,rows){const total=rows.reduce((n,r)=>n+r.count,0);return `<section class="card"><h2>${esc(title)}</h2>${rows.length?rows.map(r=>`<div class="status-line"><div><span>${esc(businessStatuses[r.status]||r.status)}</span><strong>${fmt(r.count)}</strong></div><progress max="${total||1}" value="${r.count}" aria-label="${esc(businessStatuses[r.status]||r.status)}"></progress></div>`).join(''):'<p class="empty">Chưa có dữ liệu.</p>'}</section>`}
async function overview(){
  renderOverviewBase();
  $('#main .hero')?.remove();
  $('#main .pagehead h1').textContent='Tổng quan dữ liệu mô phỏng';
  $('#main .pagehead>a').outerHTML='<div class="actions overview-shortcuts"><button class="btn" id="jump-crawler">Cào Tiki</button><a class="btn secondary" href="#sync">Đồng bộ Tiki</a><button class="btn secondary" id="jump-reset">Chạy lại từ đầu</button></div>';
  const loading=document.createElement('section');loading.id='oltp-dashboard';loading.innerHTML='<div class="card">Đang đọc thống kê OLTP…</div>';
  $('#main .pagehead').after(loading);
  $('#main').insertAdjacentHTML('beforeend',`<div class="sectionhead"><h2>Điều khiển dữ liệu</h2></div><div class="grid2"><section class="card"><h2>Cào sản phẩm từ Tiki</h2><p class="subtitle">Chạy crawler hiện có, lưu vào SQLite. Bạn tự kiểm tra và đồng bộ sang OLTP ở bước sau.</p><div class="connection-block">${esc(state.settings?.source||'Chưa thiết lập nguồn SQLite')}</div><div class="formgrid" style="margin-top:16px">${field('ID danh mục gốc, cách nhau bằng dấu phẩy (trống = tất cả)','crawl-categories','')}${field('Nghỉ giữa request: nhỏ nhất (giây)','crawl-min',4,'number','min="0" max="300" step="0.5"')}${field('Nghỉ giữa request: lớn nhất (giây)','crawl-max',8,'number','min="0" max="300" step="0.5"')}${field('Mã lượt cào cần tiếp tục (không bắt buộc)','crawl-resume','')}</div><div class="actions"><button class="btn" id="start-crawler">Bắt đầu cào Tiki</button><button class="btn secondary" id="refresh-crawler">Làm mới trạng thái</button></div><div id="crawler-feedback"></div><div id="crawler-status"></div></section><section class="card danger-zone"><span class="eyebrow">CHẠY LẠI TỪ ĐẦU</span><h2>Xóa toàn bộ dữ liệu OLTP</h2><p>Xóa tất cả các bảng dữ liệu, kể cả sản phẩm, người bán, danh mục, dữ liệu nền và nghiệp vụ.</p><p class="subtitle">Giữ SQLite crawler, thiết lập và cấu hình kịch bản. Checkpoint được đưa về ban đầu. Sau khi xóa: Đồng bộ Tiki → Tạo dữ liệu nền → Lập kế hoạch và chạy lại.</p><div class="actions"><button class="btn danger" id="preview-reset">Xem trước dữ liệu sẽ xóa</button></div><div id="reset-feedback"></div><div id="reset-preview"></div></section></div>`);
  $('#jump-crawler').onclick=()=>$('#crawl-categories').scrollIntoView({behavior:'smooth',block:'center'});
  $('#jump-reset').onclick=()=>$('#preview-reset').scrollIntoView({behavior:'smooth',block:'center'});
  $('#start-crawler').onclick=e=>busy(e.currentTarget,async()=>{
    const raw=$('#crawl-categories').value.trim();
    const ids=raw?raw.split(',').map(v=>/^\d+$/.test(v.trim())?Number(v.trim()):NaN):[];
    if(ids.some(v=>!Number.isSafeInteger(v)||v<=0))throw Error('Nhập các ID danh mục số nguyên dương, cách nhau bằng dấu phẩy.');
    await api('crawler','POST',{category_ids:ids,delay_min:Number($('#crawl-min').value),delay_max:Number($('#crawl-max').value),resume_run:$('#crawl-resume').value.trim(),request_key:crypto.randomUUID()});
    notice('#crawler-feedback','Đã xếp lượt cào. Chỉ ghi vào SQLite, chưa đồng bộ OLTP.');await drawCrawler();
  },'#crawler-feedback');
  $('#refresh-crawler').onclick=e=>busy(e.currentTarget,drawCrawler,'#crawler-feedback');
  $('#preview-reset').onclick=e=>busy(e.currentTarget,async()=>{
    const preview=await api('reset-previews','POST',{});
    $('#reset-preview').innerHTML=`<div class="notice error">Sẽ xóa ${fmt(preview.total)} dòng trong ${Object.keys(preview.counts).length} bảng OLTP. Không có thao tác khôi phục tự động.</div><details><summary>Số dòng từng bảng</summary>${table(Object.entries(preview.counts).map(([name,n])=>({'Bảng':tableLabels[name]||name,'Số dòng':n})))}</details><div class="field" style="margin-top:16px"><label for="reset-confirm">Nhập XOA TOAN BO để xác nhận</label><input id="reset-confirm" autocomplete="off" placeholder="XOA TOAN BO"></div><div class="actions"><button class="btn danger" id="confirm-reset" disabled>Xóa toàn bộ OLTP</button></div>`;
    $('#reset-confirm').oninput=()=>{$('#confirm-reset').disabled=$('#reset-confirm').value!=='XOA TOAN BO'};
    $('#confirm-reset').onclick=event=>busy(event.currentTarget,async()=>{
      const j=await api('jobs/reset','POST',{preview:preview.id,confirmation:$('#reset-confirm').value,request_key:crypto.randomUUID()});
      planId='';syncId='';currentJob=j.id;location.hash='monitor';
    },'#reset-feedback');
  },'#reset-feedback');
  await Promise.all([drawDashboard(),drawCrawler()]);
  poll=setInterval(()=>{if(location.hash==='#overview'||!location.hash)Promise.all([drawDashboard(),drawCrawler()]).catch(()=>{})},5000);
}
function dailyOrderChart(rows){
  if(!rows.length)return '<p class="empty">Chưa có đơn hàng.</p>';
  const max=Math.max(1,...rows.map(r=>r.orders));
  return '<div class="daily-chart" role="img" aria-label="Số đơn theo ngày mô phỏng">'+rows.map(r=>`<div class="daily-column" title="${esc(r.day)}: ${fmt(r.orders)} đơn"><strong>${fmt(r.orders)}</strong><span style="height:${Math.max(2,r.orders/max*130)}px"></span><small>${esc(r.day.slice(5))}</small></div>`).join('')+'</div>';
}
async function drawDashboard(){
  const d=await api('dashboard');if(!$('#oltp-dashboard'))return;
  if(!d.ready){$('#oltp-dashboard').innerHTML='<div class="notice">Chuẩn bị môi trường để xem thống kê OLTP.</div>';return}
  const c=(await api('overview')).counts;
  if(!$('#oltp-dashboard'))return;
  const dailyOpen=Boolean($('#oltp-dashboard details')?.open);
  $('#oltp-dashboard').innerHTML=`<div class="sectionhead"><div><h2>Dữ liệu hiện có trong OLTP</h2><p class="label">Đọc trực tiếp database nghiệp vụ · Cập nhật ${esc(d.checked_at)} · Tự làm mới mỗi 5 giây</p></div><a class="btn secondary small" href="#history">Xem các bảng ↗</a></div>`+
    metricCards([['Đơn hàng',fmt(c.orders),'Tất cả trạng thái'],['Khách hàng',fmt(c.customers),'Gồm khách nền và khách đăng ký'],['Phiên truy cập',fmt(c.sessions),`${fmt(c.page_events)} sự kiện truy cập`],['Số dòng OLTP',fmt(Object.values(c).reduce((a,b)=>a+b,0)),`${Object.keys(c).length} bảng nghiệp vụ`]])+
    metricCards([['Giá trị toàn bộ đơn',fmt(d.order_amount)+' ₫','Gồm cả đơn hủy và chưa thanh toán'],['Giá trị đơn hoàn tất',fmt(d.completed_amount)+' ₫','Tổng final_amount của đơn hoàn tất'],['Thanh toán thành công',fmt(d.paid_amount)+' ₫','Tổng paid_amount trạng thái thành công'],['Chi phí quảng cáo',fmt(d.ad_cost)+' ₫','Tổng chi phí trong nhật ký quảng cáo']])+
    `<section class="card"><h2>Đơn hàng theo ngày mô phỏng</h2><p class="label">30 ngày có đơn gần nhất · Nhóm theo ngày tạo đơn · Giá trị gồm tất cả trạng thái</p>${dailyOrderChart(d.daily_orders)}<details><summary>Xem số liệu từng ngày</summary>${table(d.daily_orders.map(r=>({'Ngày':r.day,'Số đơn':fmt(r.orders),'Giá trị đơn (đồng)':fmt(r.amount)})))}</details></section>`;
  if($('#oltp-dashboard details'))$('#oltp-dashboard details').open=dailyOpen;
}
async function drawCrawler(){
  const data=await api('crawler');if(!$('#crawler-status'))return;
  const j=data.latest;const active=j&&['QUEUED','RUNNING','STOPPING'].includes(j.status);
  $('#start-crawler').disabled=Boolean(active)||!data.source;
  const logsOpen=Boolean($('#crawler-status details')?.open);
  $('#crawler-status').innerHTML=j?`<div class="sectionhead"><h3>Lượt cào gần nhất</h3>${badge(j.status)}</div><p>${esc(j.message)}</p><p class="label">Bắt đầu: ${esc(j.started_at||j.created_at)} · Kết thúc: ${esc(j.finished_at||'—')}</p>${j.crawl_run_id?`<p class="label">Mã tiếp tục: <code>${esc(j.crawl_run_id)}</code></p>`:''}${active?'<button class="btn secondary small" id="stop-crawler">Dừng cào, giữ các trang đã lưu</button>':''}<details><summary>Xem log crawler</summary><pre class="crawler-log">${esc(j.log_tail||'Chờ worker cào dữ liệu…')}</pre></details>`:'<p class="label">Chưa có lượt cào được kích hoạt từ giao diện.</p>';
  if($('#crawler-status details'))$('#crawler-status details').open=logsOpen;
  if($('#stop-crawler'))$('#stop-crawler').onclick=e=>busy(e.currentTarget,async()=>{await api(`crawler/${j.id}/stop`,'POST',{});notice('#crawler-feedback','Đã gửi yêu cầu dừng crawler.');await drawCrawler()},'#crawler-feedback');
}
async function syncPage(){
  renderSyncBase();
  $('#main .pagehead').insertAdjacentHTML('afterend','<section class="card" id="sync-status-card"><h2>Theo dõi nguồn & đồng bộ</h2><div id="sync-status-detail">Đang đọc lịch sử…</div><div class="actions"><button class="btn secondary" id="check-source">Kiểm tra sản phẩm mới trong SQLite</button></div><div id="source-feedback"></div><div id="source-check-result"></div></section>');
  const result=await api('sync-status');const last=result.last_sync;
  $('#sync-status-detail').innerHTML=last?`<p>Đồng bộ thành công gần nhất: <strong>${esc(last.finished_at)}</strong></p><p class="label">Đã xét ${fmt(last.completed)} sản phẩm. Đây là thời gian thực, không phải ngày mô phỏng.</p>`:'<p>Chưa có lần đồng bộ thành công trong dữ liệu hiện tại.</p>';
  if(result.last_attempt&&result.last_attempt.id!==last?.id)$('#sync-status-detail').insertAdjacentHTML('beforeend',`<p class="label">Lần thực hiện gần nhất: ${esc(result.last_attempt.created_at)} · ${esc(statuses[result.last_attempt.status]||result.last_attempt.status)}${result.last_attempt.archived?' · Thuộc dữ liệu đã xóa':''}</p>`);
  $('#check-source').onclick=e=>busy(e.currentTarget,async()=>{
    const p=await api('source-check','POST',{});
    $('#source-check-result').innerHTML=metricCards([['Sản phẩm trong SQLite',fmt(p.source_count),'Toàn bộ sản phẩm nguồn'],['ID sản phẩm chưa có',fmt(p.source_new),`${fmt(p.new)} sản phẩm mới đủ điều kiện thêm`],['ID sản phẩm đã có',fmt(p.source_existing),'Giữ nguyên theo rule append-only'],['Bản ghi có lỗi',fmt(p.errors.length),'Cần kiểm tra SKU, chào bán hoặc trường bắt buộc']])+`<p class="label">Kiểm tra lúc ${esc(p.checked_at)}. Đếm sản phẩm, không đếm các dòng raw hoặc bảng phụ của crawler.</p>${p.errors.length?'<details><summary>Xem lỗi dữ liệu</summary>'+table(p.errors)+'</details>':''}`;
    notice('#source-feedback',p.new?'Có sản phẩm mới. Hãy Xem trước đồng bộ bên dưới để chọn giới hạn và thực hiện.':'Chưa có sản phẩm mới hợp lệ để đồng bộ.');
  },'#source-feedback');
}
