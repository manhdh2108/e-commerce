/* Read-only presentation: internal action keys never become primary UI labels. */
(function (root) {
  const names = {catalog:'Sản phẩm & Người bán',orders:'Khách hàng & Đơn hàng',warehouse:'Kho vận',marketing:'Marketing',analytics:'Hành vi truy cập',finance:'Tài chính'};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = value => Number(value || 0).toLocaleString('vi-VN');
  function day(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
    return match ? `${match[3]}/${match[2]}/${match[1]}` : value || 'Chưa chọn ngày';
  }
  function index(catalog) {
    return Object.fromEntries(catalog.flatMap(system => system.actions.map(action => [action.code, {...action, system:system.key, systemName:names[system.key] || system.title, group:action.group.replace(/^\d+(?:\.\d+)*\.?\s*/, '').replace(/^Nhóm\s+/, '')}])));
  }
  function action(catalog, code) {
    return index(catalog)[code] || {label:'Hoạt động chưa có mô tả',group:'Chưa xác định',systemName:'Hệ thống',fields:[],code};
  }
  function message(catalog, raw) {
    let output = String(raw || '');
    const list = index(catalog);
    for (const [code, a] of Object.entries(list).sort(([a],[b])=>b.length-a.length)) {
      if (output.startsWith(`${code} · `)) return a.label;
      output = output.split(code).join(a.label);
    }
    const tables = {inventory_levels:'tồn kho',shipments:'vận đơn',payments:'giao dịch thanh toán',products:'sản phẩm',sellers:'người bán',customers:'khách hàng',sessions:'phiên truy cập',cart_items:'mục giỏ hàng',orders:'đơn hàng',promotions:'ưu đãi',seller_payouts:'hồ sơ đối soát',marketing_campaigns:'chiến dịch quảng cáo'};
    for (const [key, value] of Object.entries(tables)) output = output.split(key).join(value);
    return output;
  }
  function count(cfg) {
    return cfg.mode === 'all' ? 'Tự xử lý khi có yêu cầu đủ điều kiện' : `${number(cfg.count)} lần/ngày`;
  }
  function specials(cfg) {
    if (cfg.mode === 'all') return 'Theo lượng yêu cầu thực tế, không dùng số lần riêng';
    const rows = Object.entries(cfg.special || {}).sort(([a],[b]) => a.localeCompare(b));
    return rows.length ? rows.map(([d,n]) => `${day(d)}: ${number(n)} lần`).join('\n') : 'Giữ số lần của ngày thường';
  }
  function specialCell(cfg) {
    const entries=Object.keys(cfg.special||{});
    const text=esc(specials(cfg));
    return cfg.mode!=='all' && entries.length>7 ? `<details><summary>${entries.length} ngày có cấu hình riêng</summary><div class="schedule-details">${text}</div></details>`:text;
  }
  function valueLabel(field, value) {
    if (field.key === 'amount' || field.key === 'min_order') return `${number(value)} đồng`;
    if (['rate','success_rate'].includes(field.key)) return `${number(value)}%`;
    if (field.type === 'date') return day(value);
    const words = {direct:'Đặt trực tiếp',linked:'Từ phiên và giỏ hàng',none:'Không áp ưu đãi',auto:'Tự chọn hợp lệ',category:'Danh mục chỉ định',all_leaf:'Tất cả danh mục lá',all_failed:'Mọi vận đơn giao thất bại',attempts_exhausted:'Chỉ khi hết số lần giao lại',Web:'Website',App:'Ứng dụng',Livestream:'Phát trực tiếp',COD:'Thanh toán khi nhận hàng',Momo:'Ví MoMo','ZaloPay':'Ví ZaloPay','Credit Card':'Thẻ tín dụng','Bank Transfer':'Chuyển khoản',Mobile:'Điện thoại',Desktop:'Máy tính',Tablet:'Máy tính bảng',Organic:'Truy cập tự nhiên',Direct:'Truy cập trực tiếp','Normal':'Thông thường',Preferred:'Ưu tiên',Mall:'Gian hàng Mall',Member:'Thành viên',Silver:'Bạc',Gold:'Vàng',Platinum:'Bạch kim'};
    return words[value] || String(value);
  }
  function parameters(a, cfg) {
    const rows = a.fields.flatMap(field => {
      const value = cfg.params?.[field.key] ?? field.default;
      return value === '' || value === null || value === undefined ? [] : [{label:field.label.replace(/\s*\(trống:.*\)$/,''),value:valueLabel(field,value)}];
    });
    if(cfg.actor_pool)rows.push({label:'Nhóm thực hiện',value:cfg.actor_pool});
    if(cfg.schedule?.start)rows.push({label:'Khung giờ',value:cfg.schedule.start+' – '+cfg.schedule.end});
    if(cfg.schedule?.windows)rows.push({label:'Phân bố giờ hoạt động',value:cfg.schedule.windows.map(w=>w.start+' – '+w.end+' (trọng số '+w.weight+')').join('; ')});
    if(cfg.schedule?.after_seconds)rows.push({label:'Độ trễ xử lý từ đầu vào',value:cfg.schedule.after_seconds.min+' – '+cfg.schedule.after_seconds.max+' giây'});
    if(cfg.variant_mode==='cycle')rows.push({label:'Cách chọn nhóm tham số',value:'Luân phiên từng nhóm'});
    if(cfg.phase!==undefined)rows.push({label:'Thứ tự xử lý',value:cfg.phase});
    if(cfg.preferences?.products)rows.push({label:'Ưu tiên sản phẩm',value:cfg.preferences.products.source==='session_views'?'Sản phẩm đã xem trong phiên':'Sở thích từ tìm kiếm trong phiên'});
    if(cfg.schedule?.offset_seconds)rows.push({label:'Theo phiên',value:'Độ trễ từ lúc mở phiên (giây): '+cfg.schedule.offset_seconds.min+' – '+cfg.schedule.offset_seconds.max});
    if(cfg.parameter_rules?.length)rows.push({label:'Tham số theo điều kiện',value:cfg.parameter_rules.length+' quy tắc, ưu tiên quy tắc khớp đầu tiên'});
    if(cfg.delay_days)rows.push({label:'Độ trễ tối thiểu',value:cfg.delay_days+' ngày'});
    if(cfg.variants?.length){const total=cfg.variants.reduce((n,r)=>n+r.weight,0);for(const row of cfg.variants){rows.push({label:'Nhóm '+row.name,value:`Trọng số ${row.weight}/${total}: `+parameters(a,{params:{...cfg.params,...row.params}}).map(p=>p.label+': '+p.value).join('; ')})}}
    return rows;
  }
  function technical(code) {
    return `<details class="technical"><summary>Chi tiết kỹ thuật</summary><span>Mã nội bộ: <code>${esc(code)}</code></span></details>`;
  }
  function summary(catalog, config) {
    const enabled = catalog.flatMap(s => s.actions.filter(a => config[a.code]?.enabled));
    const specialDays = new Set(enabled.flatMap(a => config[a.code].mode === 'all' ? [] : Object.keys(config[a.code].special || {})));
    const stats = `<div class="summary-metrics"><span><strong>${catalog.length}</strong> hệ thống</span><span><strong>${enabled.length}</strong> hành động đang bật</span><span><strong>${enabled.filter(a=>config[a.code].mode==='all').length}</strong> xử lý tự động</span><span><strong>${specialDays.size}</strong> ngày có số lần riêng</span></div>`;
    const sections = catalog.map(system => {
      const active = system.actions.filter(a => config[a.code]?.enabled);
      const disabled = system.actions.filter(a => !config[a.code]?.enabled);
      return `<section class="card scenario-system"><div class="card-header"><h2>${esc(names[system.key] || system.title)}</h2><span class="badge ${active.length?'green':''}">${active.length} hành động bật</span></div>${active.length ? `<div class="tablewrap"><table class="readable-table"><thead><tr><th>Ai thực hiện?</th><th>Hành động</th><th>Ngày thường</th><th>Ngày đặc biệt</th></tr></thead><tbody>${active.map(a=>{
        const cfg=config[a.code], info=action(catalog,a.code), params=parameters(a,cfg);
        return `<tr><td data-label="Ai thực hiện?">${esc(info.group)}</td><td data-label="Hành động"><strong>${esc(a.label)}</strong><small class="action-unit">Một lần: ${esc(a.unit)}</small>${params.length?`<details class="parameter-details"><summary>Xem ${params.length} tham số</summary><dl>${params.map(p=>`<dt>${esc(p.label)}</dt><dd>${esc(p.value)}</dd>`).join('')}</dl></details>`:'<small class="action-unit">Tự chọn đối tượng hợp lệ</small>'}${technical(a.code)}</td><td data-label="Ngày thường">${esc(count(cfg))}</td><td data-label="Ngày đặc biệt" class="special-lines">${specialCell(cfg)}</td></tr>`;
      }).join('')}</tbody></table></div>`:'<p>Chưa bật hành động cho hệ thống này.</p>'}<details class="disabled-actions"><summary>${disabled.length} hành động đang tắt</summary><ul>${disabled.map(a=>`<li>${esc(a.label)}${!a.available?` <span class="badge orange">Chưa hỗ trợ</span><small>${esc(a.unavailable_reason)}</small>`:''}</li>`).join('')}</ul></details></section>`;
    }).join('');
    return stats + sections;
  }
  function plan(catalog, plan) {
    return plan.days.map((d,i) => `<details class="card day-plan" ${i===0?'open':''}><summary><strong>Ngày ${esc(day(d.day))}</strong><span>${number(d.total)} lần theo số lượng đã đặt${d.automatic?` · ${d.automatic} hành động tự xử lý`:''}</span></summary>${catalog.map(system=>{
      const rows=d.actions.filter(a=>a.system===system.key);
      if(!rows.length)return '';
      return `<section class="plan-system"><h3>${esc(names[system.key] || system.title)}</h3><div class="tablewrap"><table class="readable-table"><thead><tr><th>Ai thực hiện?</th><th>Hành động</th><th>Số lần trong ngày</th></tr></thead><tbody>${rows.map(row=>{const a=action(catalog,row.code);return `<tr><td data-label="Ai thực hiện?">${esc(a.group)}</td><td data-label="Hành động"><strong>${esc(a.label)}</strong>${technical(row.code)}</td><td data-label="Số lần trong ngày">${esc(typeof row.requested==='number'?`${number(row.requested)} lần`:'Tự xử lý khi có yêu cầu đủ điều kiện')}</td></tr>`}).join('')}</tbody></table></div></section>`;
    }).join('')}</details>`).join('');
  }
  const api={names,esc,day,index,action,message,count,specials,valueLabel,parameters,technical,summary,plan};
  if (typeof module !== 'undefined' && module.exports) module.exports=api;
  else root.MockPresentation=api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
