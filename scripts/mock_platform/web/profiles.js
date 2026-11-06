/* Human-readable parameter bundles. No JSON editing required. */
function profileInput(f,value){
  if(f.type==='select')return `<select data-profile-param="${esc(f.key)}">${f.options.map(v=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(P.valueLabel(f,v)||'Không lọc')}</option>`).join('')}</select>`;
  return `<input data-profile-param="${esc(f.key)}" type="${f.type}" value="${esc(value??'')}" ${f.min!==undefined?`min="${f.min}"`:''} ${f.max!==undefined?`max="${f.max}"`:''}>`;
}
function profileRow(action,row){
  return `<section class="profile-row"><div class="formgrid"><div class="field"><label>Tên nhóm</label><input data-profile-name value="${esc(row.name)}"></div><div class="field"><label>Trọng số (không phải số lượt)</label><input data-profile-weight type="number" min="1" max="10000" value="${esc(row.weight)}"></div></div><div class="formgrid">${action.fields.map(f=>`<div class="field"><label>${esc(f.label)}</label>${profileInput(f,row.params[f.key]??getcfg(action.code).params[f.key]??f.default??'')}</div>`).join('')}</div><button class="btn secondary small" type="button" data-remove-profile>Xóa nhóm này</button></section>`;
}
function mountActionProfiles(a,c){
  if(['PAY-01','ORD-01','DSP-01','CAR-01','CAR-02','CAR-03','CAR-04','CUS-09','SUP-01','SUP-02','WH-04','PAY-02','CAR-05','CAR-06'].includes(a.code))$('#save-draft').parentElement.insertAdjacentHTML('beforebegin',`<div class="field"><label>Độ trễ tối thiểu từ bước trước (ngày)</label><input id="action-delay" type="number" min="0" max="365" value="${c.delay_days||0}"><small>0: có thể xử lý cùng ngày. Yêu cầu chưa đến hạn được giữ cho ngày sau.</small></div>`);
  $('#save-draft').parentElement.insertAdjacentHTML('beforebegin',`<details class="profile-editor" ${c.variants?.length?'open':''}><summary>Phân bố nhiều nhóm tham số trong ngày</summary><p>Các lượt chọn một nhóm theo trọng số. Ví dụ 7 và 3 tương ứng xác suất 70% và 30%; số lượt thực tế có thể khác. Không có nhóm: dùng cấu hình riêng bên trên.</p><div id="profile-rows">${(c.variants||[]).map(r=>profileRow(a,r)).join('')}</div><button class="btn secondary small" id="add-profile" type="button">+ Thêm nhóm tham số</button></details>`);
  $('#save-draft').parentElement.insertAdjacentHTML('beforebegin',`<details><summary>Người thực hiện, phạm vi và thời gian</summary><p>Chọn ID nhóm đã khai báo trong Thiết lập. Để trống để giữ cách chọn cũ.</p><div class="formgrid"><div class="field"><label for="action-actor-pool">Nhóm người thực hiện</label><input id="action-actor-pool" value="${esc(c.actor_pool||'')}"></div><div class="field"><label for="schedule-start">Bắt đầu khung giờ</label><input id="schedule-start" type="time" step="1" value="${esc(c.schedule?.start||'')}"></div><div class="field"><label for="schedule-end">Kết thúc khung giờ</label><input id="schedule-end" type="time" step="1" value="${esc(c.schedule?.end||'')}"></div></div><label for="action-parameter-rules">Tham số theo thuộc tính người thực hiện / đối tượng (JSON)</label><textarea id="action-parameter-rules" rows="5">${esc(JSON.stringify(c.parameter_rules||[],null,2))}</textarea><label for="schedule-offset">Độ trễ từ lúc mở phiên (giây, JSON; chỉ dùng hành vi phiên/checkout liên kết)</label><textarea id="schedule-offset" rows="3">${esc(c.schedule?.offset_seconds?JSON.stringify(c.schedule.offset_seconds,null,2):'')}</textarea><label for="action-selection">Phạm vi đối tượng (JSON bảng → thuộc tính → danh sách)</label><textarea id="action-selection" rows="4">${esc(JSON.stringify(c.selection||{},null,2))}</textarea>${a.code.endsWith('WEB-01')?`<label for="session-duration">Phân bố thời lượng phiên (giây, JSON; trống: giữ lịch cũ)</label><textarea id="session-duration" rows="3">${esc(c.schedule?.duration_seconds?JSON.stringify(c.schedule.duration_seconds,null,2):'')}</textarea>`:''}</details>`);
  $('#action-selection').insertAdjacentHTML('afterend',`<label for="action-runtime-options">Lịch theo trọng số, độ trễ, cách chọn sản phẩm và thứ tự nhóm tham số (JSON)</label><textarea id="action-runtime-options" rows="7">${esc(JSON.stringify({phase:c.phase,variant_mode:c.variant_mode||'random',preferences:c.preferences||{},schedule:Object.fromEntries(['windows','after_seconds'].filter(k=>c.schedule?.[k]!==undefined).map(k=>[k,c.schedule[k]]))},null,2))}</textarea>`);
  const poolField=$('#action-actor-pool');poolField.setAttribute('list','actor-pool-options');poolField.insertAdjacentHTML('afterend','<datalist id="actor-pool-options"></datalist>');
  api('entity-profile').then(p=>{if($('#action-actor-pool')!==poolField)return;const system=catalog.find(s=>s.actions.some(x=>x.code===a.code));const role=system.key+'/'+a.group;$('#actor-pool-options').innerHTML=(p.actors||[]).filter(pool=>pool.roles.includes(role)).map(pool=>`<option value="${esc(pool.id)}">${esc(a.group)}</option>`).join('')}).catch(()=>{});
  const wire=()=>document.querySelectorAll('[data-remove-profile]').forEach(b=>b.onclick=()=>b.closest('.profile-row').remove());
  $('#add-profile').onclick=()=>{const n=$('#profile-rows').children.length;$('#profile-rows').insertAdjacentHTML('beforeend',profileRow(a,{name:'Nhóm '+(n+1),weight:1,params:{}}));wire()};wire();
}
function captureActionProfiles(c){
  if($('#action-actor-pool')){
    const pool=$('#action-actor-pool').value.trim();if(pool)c.actor_pool=pool;else delete c.actor_pool;
    c.selection=JSON.parse($('#action-selection').value||'{}');
    c.parameter_rules=JSON.parse($('#action-parameter-rules').value||'[]');
    const start=$('#schedule-start').value,end=$('#schedule-end').value;
    const offset=$('#schedule-offset').value.trim();
    const duration=$('#session-duration')?.value.trim();
    if(start||end||offset||duration){c.schedule={};if(start||end)Object.assign(c.schedule,{start,end});if(offset)c.schedule.offset_seconds=JSON.parse(offset);if(duration)c.schedule.duration_seconds=JSON.parse(duration)}else delete c.schedule;
  }
  if($('#action-runtime-options')){
    const extra=JSON.parse($('#action-runtime-options').value||'{}');
    if(!extra || Array.isArray(extra) || Object.keys(extra).some(k=>!['phase','variant_mode','preferences','schedule'].includes(k)))throw new Error('Tùy chọn thực thi không hợp lệ.');
    if(extra.phase!==undefined)c.phase=extra.phase;else delete c.phase;
    if(extra.variant_mode)c.variant_mode=extra.variant_mode;
    if(extra.preferences)c.preferences=extra.preferences;
    if(extra.schedule && Object.keys(extra.schedule).some(k=>!['windows','after_seconds'].includes(k)))throw new Error('Chỉ hỗ trợ windows và after_seconds trong lịch nâng cao.');
    if(extra.schedule && Object.keys(extra.schedule).length)c.schedule={...(c.schedule||{}),...extra.schedule};
  }
  if($('#action-delay'))c.delay_days=Number($('#action-delay').value);
  if(!$('#profile-rows'))return;
  const rows=[...document.querySelectorAll('.profile-row')].map(row=>({name:row.querySelector('[data-profile-name]').value.trim(),weight:Number(row.querySelector('[data-profile-weight]').value),params:Object.fromEntries([...row.querySelectorAll('[data-profile-param]')].map(el=>[el.dataset.profileParam,el.type==='number'?(el.value===''?null:Number(el.value)):el.value]))}));
  if(rows.length)c.variants=rows;else delete c.variants;
}
async function mountEntityProfiles(){
  const host=document.createElement('section');host.className='card';host.id='entity-profile-editor';$('#main').appendChild(host);
  const [profile,policy]=await Promise.all([api('entity-profile'),api('business-policy')]);if(!host.isConnected||$('#entity-profile-editor')!==host)return;
  const columns={locations:{province:'Tỉnh / thành',city:'Thành phố',ward:'Phường / khu vực',district:'Quận / huyện (có thể trống)',street:'Tên đường mô phỏng'},warehouses:{warehouse_code:'Mã kho',warehouse_name:'Tên kho',province:'Tỉnh / thành',city:'Thành phố',address:'Địa chỉ'},carriers:{carrier_code:'Mã vận chuyển',carrier_name:'Tên đơn vị'}};
  const row=(key,data)=>`<tr>${Object.keys(columns[key]).map(k=>`<td><input data-entity-column="${k}" aria-label="${esc(columns[key][k])}" value="${esc(data[k]??'')}"></td>`).join('')}<td><button class="btn secondary small" data-remove-entity type="button">Xóa</button></td></tr>`;
  host.innerHTML=`<h2>Chính sách mô phỏng</h2><p>Giả định để thử nghiệm: tối đa một voucher hàng và một voucher phí ship; trả hàng hoàn phần tiền hàng đã giảm giá, không hoàn phí giao; đối soát sau cửa sổ trả và khi đã hết nghĩa vụ chờ. Không phải chính sách của Tiki.</p><div class="formgrid">${[["return_window_days","Cửa sổ yêu cầu trả (ngày)"],["payout_hold_days","Giữ tiền tối thiểu trước đối soát (ngày)"],["max_delivery_attempts","Tối đa số lần giao"]].map(([key,label])=>`<div class="field"><label>${label}</label><input id="policy-${key}" type="number" min="1" max="${key==='max_delivery_attempts'?10:365}" value="${policy[key]}"></div>`).join('')}</div><button class="btn secondary" id="save-business-policy">Lưu chính sách cho kế hoạch mới</button><div id="policy-feedback"></div><hr><h2>Hồ sơ dữ liệu mô phỏng</h2><p>Tên, điện thoại và địa chỉ đều là dữ liệu tổng hợp để thử nghiệm. Bộ địa phương dưới đây không đại diện địa giới hành chính thật. Lưu chỉ áp dụng cho job mới; không sửa hồ sơ đã sinh.</p><div class="formgrid">${[['surnames','Họ'],['given_names','Tên'],['phone_prefixes','Đầu số điện thoại']].map(([key,label])=>`<div class="field"><label>${label} (mỗi dòng một giá trị)</label><textarea id="entity-${key}" rows="5">${esc(profile[key].join('\n'))}</textarea></div>`).join('')}</div>${Object.entries(columns).map(([key,cols])=>`<details open><summary>${{locations:'Địa phương theo bộ nhất quán',warehouses:'Danh sách kho',carriers:'Đơn vị vận chuyển'}[key]}</summary><div class="tablewrap"><table><thead><tr>${Object.values(cols).map(v=>`<th>${v}</th>`).join('')}<th></th></tr></thead><tbody data-entity-table="${key}">${profile[key].map(r=>row(key,r)).join('')}</tbody></table></div><button class="btn secondary small" data-add-entity="${key}">+ Thêm dòng</button></details>`).join('')}<div class="notice">Kho và carrier được tạo khi chạy dữ liệu nền lần đầu. Tồn đầu là lượng của mỗi SKU tại mỗi kho, không phải tổng chia đều. Sau bootstrap, thêm dòng ở đây chưa tự tạo kho/carrier mới trong OLTP.</div><button class="btn" id="save-entity-profile">Lưu hồ sơ mô phỏng</button><div id="entity-feedback"></div>`;
  const bootstrapProfileNotice=document.createElement('div');bootstrapProfileNotice.className='notice';bootstrapProfileNotice.id='bootstrap-profile-notice';$('#bootstrap').before(bootstrapProfileNotice);
  const updateBootstrapProfile=p=>{const override=Array.isArray(p.inventory);$('#stock').disabled=override;bootstrapProfileNotice.textContent=override?`Hồ sơ đã lưu có ${p.inventory.length} quy tắc tồn theo nhóm. Khi tạo dữ liệu nền, hệ thống dùng các quy tắc này; ô tồn chung không được sử dụng.`:'Hồ sơ đang dùng tồn chung: mỗi SKU tại mỗi kho nhận lượng ở ô trên. Chỉ tạo dữ liệu nền một lần.';};updateBootstrapProfile(profile);
  const extraKeys=["customer_attributes","seller_attributes","actors","inventory","channels","payment_methods","bootstrap"];
  const advanced=()=>Object.fromEntries(extraKeys.filter(k=>profile[k]!==undefined).map(k=>[k,profile[k]]));
  host.querySelector("#save-entity-profile").insertAdjacentHTML("beforebegin",`<details><summary>Quần thể tác động và thuộc tính mở rộng</summary><p>Nhập JSON hoặc dùng file thiết lập. Giá trị, trọng số, phân công vai trò và tồn theo nhóm được lưu riêng với dữ liệu nghiệp vụ. Không sửa các thực thể OLTP đã sinh.</p><textarea id="entity-advanced" aria-label="Cấu hình quần thể và thuộc tính" rows="16">${esc(JSON.stringify(advanced(),null,2))}</textarea></details>`);
  const populationSummary=()=>{
    const target=host.querySelector('#population-summary');
    try{const p=JSON.parse($('#entity-advanced').value||'{}');const labels={customers:'Khách đăng ký',sellers:'Người bán',carriers:'Đơn vị vận chuyển',virtual:'Nhân sự / dịch vụ / khách vãng lai'};
      target.innerHTML=`<h3>Các nhóm tác động trong hồ sơ</h3>${(p.actors||[]).length?table(p.actors.map(a=>({'Nhóm':a.id,'Loại':labels[a.entity]||a.entity,'Quần thể':a.entity==='virtual'?a.count||1:'Chọn từ dữ liệu OLTP','Vai trò':(a.roles||[]).map(r=>r.split('/').slice(1).join('/')).join('; '),'Thuộc tính':Object.keys(a.attributes||{}).join(', ')}))):'<p class="label">Chưa khai báo nhóm tác động mở rộng. Các hành động vẫn có thể dùng chế độ tương thích cũ.</p>'}${p.inventory?'<p class="notice">Có quy tắc tồn theo nhóm: chúng thay thế số tồn chung ở ô dữ liệu nền. Áp dụng khi bootstrap môi trường mới; không sửa tồn hiện tại.</p>':''}`;
    }catch{target.innerHTML='<p class="notice error">JSON mở rộng chưa hợp lệ. Chưa có thay đổi nào được lưu.</p>'}
  };
  host.querySelector('#entity-advanced').insertAdjacentHTML('afterend','<div id="population-summary"></div>');
  $('#entity-advanced').addEventListener('input',populationSummary);populationSummary();
  const wire=()=>host.querySelectorAll('[data-remove-entity]').forEach(b=>b.onclick=()=>b.closest('tr').remove());wire();
  host.querySelectorAll('[data-add-entity]').forEach(b=>b.onclick=()=>{host.querySelector(`[data-entity-table="${b.dataset.addEntity}"]`).insertAdjacentHTML('beforeend',row(b.dataset.addEntity,{}));wire()});
  mountSettingsTransfer(host,preview=>{
    if(preview.business_policy)for(const [key,value] of Object.entries(preview.business_policy))$('#policy-'+key).value=value;
    if(preview.entity_profile){
      const p=preview.entity_profile;
      $("#entity-advanced").value=JSON.stringify(Object.fromEntries(extraKeys.filter(k=>p[k]!==undefined).map(k=>[k,p[k]])),null,2);
      for(const key of ['surnames','given_names','phone_prefixes'])$('#entity-'+key).value=p[key].join('\n');
      for(const key of Object.keys(columns))host.querySelector(`[data-entity-table="${key}"]`).innerHTML=p[key].map(r=>row(key,r)).join('');
      wire();populationSummary();
    }
  });
  $('#save-business-policy').onclick=e=>busy(e.currentTarget,async()=>{const payload=Object.fromEntries(Object.keys(policy).map(k=>[k,Number($('#policy-'+k).value)]));await api('business-policy','PUT',payload);notice('#policy-feedback','Đã lưu. Job/đơn đã sinh giữ chính sách đã chốt; không đổi lịch sử. Hãy lập kế hoạch mới.');},'#policy-feedback');
  $('#save-entity-profile').onclick=e=>busy(e.currentTarget,async()=>{
    const payload={};for(const key of ['surnames','given_names','phone_prefixes'])payload[key]=$('#entity-'+key).value.split('\n').map(s=>s.trim()).filter(Boolean);
    for(const key of Object.keys(columns))payload[key]=[...host.querySelectorAll(`[data-entity-table="${key}"] tr`)].map(tr=>Object.fromEntries([...tr.querySelectorAll('[data-entity-column]')].map(el=>[el.dataset.entityColumn,el.value.trim()||(el.dataset.entityColumn==='district'?null:'')])));
    const extra=JSON.parse($("#entity-advanced").value||"{}");
    if(!extra || Array.isArray(extra) || Object.keys(extra).some(k=>!extraKeys.includes(k)))throw new Error("Trường hồ sơ mở rộng không hợp lệ.");
    Object.assign(payload,extra);
    await api('entity-profile','PUT',payload);updateBootstrapProfile(payload);catalog=await api('catalog');notice('#entity-feedback','Đã lưu. Hãy lập kế hoạch mới để dùng hồ sơ này. Dữ liệu OLTP đã có được giữ nguyên.');
  },'#entity-feedback');
}
