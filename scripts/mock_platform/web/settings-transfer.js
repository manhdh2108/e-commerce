/* Settings imports only fill visible forms; existing Save buttons persist explicitly. */
class SettingsImportController {
  constructor(fill,request){this.fill=fill;this.request=request;this.text='';this.generation=0;this.preview=null;}
  setText(text){this.text=text;this.generation++;this.preview=null;}
  async check(){
    const generation=++this.generation;this.preview=null;
    const result=await this.request({text:this.text});
    if(generation!==this.generation)return null;
    this.preview=result;return result;
  }
  apply(){
    if(!this.preview)throw Error('Hãy kiểm tra JSON trước khi điền form.');
    this.fill(JSON.parse(JSON.stringify(this.preview)));this.preview=null;
  }
}
function settingsPreviewMarkup(preview){
  const labels={return_window_days:'Cửa sổ yêu cầu trả hàng (ngày)',payout_hold_days:'Giữ tiền trước đối soát (ngày)',max_delivery_attempts:'Tối đa số lần giao'};
  const p=preview.business_policy,s=preview.summary;
  return `<h3>${esc(preview.name)}</h3>${p?`<dl>${Object.entries(labels).map(([key,label])=>`<dt>${label}</dt><dd>${esc(p[key])}</dd>`).join('')}</dl>`:'<p>Không thay đổi các ô chính sách.</p>'}${preview.entity_profile?`<p><strong>${esc(s.surnames)} họ · ${esc(s.given_names)} tên</strong> (tối đa ${esc(s.name_combinations)} tổ hợp), ${esc(s.phone_prefixes)} đầu số.</p><p>${esc(s.locations)} bộ địa phương ở ${esc(s.provinces)} tỉnh/thành · ${esc(s.warehouses)} kho · ${esc(s.carriers)} đơn vị vận chuyển.</p><p>${esc(s.actor_groups||0)} nhóm tác động · ${esc(s.inventory_rules||0)} quy tắc tồn theo nhóm. Xem chi tiết sau khi điền form.</p>`:'<p>Không thay đổi các ô hồ sơ thực thể.</p>'}${preview.warnings.map(w=>`<div class="notice">${esc(w)}</div>`).join('')}`;
}
function mountSettingsTransfer(host,fill){
  host.insertAdjacentHTML('afterbegin',`<details class="settings-transfer" open><summary>Nhập thiết lập bằng JSON</summary><p>Chọn file hoặc dán JSON → kiểm tra → điền vào form. Sau đó bạn có thể chỉnh tiếp và bấm các nút Lưu bên dưới. Không tự sửa dữ liệu OLTP.</p><a class="btn secondary small" href="/api/settings-template" download>Tải bản đầy đủ đa dạng</a><a class="btn secondary small" href="/api/settings-template-basic" download>Tải mẫu cơ bản: chính sách</a><div class="field" style="margin-top:16px"><label for="settings-import-file">File thiết lập JSON (tối đa 2 MiB)</label><input id="settings-import-file" type="file" accept=".json,application/json"></div><div class="field"><label for="settings-import-text">Hoặc dán nội dung JSON</label><textarea id="settings-import-text" rows="6" spellcheck="false" placeholder="Dán JSON chính sách hoặc file mock-studio-settings"></textarea></div><div class="actions"><button class="btn secondary" id="settings-import-check">Kiểm tra & xem trước</button><button class="btn" id="settings-import-fill" disabled>Điền vào biểu mẫu</button></div><div id="settings-import-feedback"></div><div id="settings-import-result"></div></details>`);
  const controller=new SettingsImportController(fill,payload=>api('settings-imports/preview','POST',payload));
  const reset=()=>{$('#settings-import-fill').disabled=true;$('#settings-import-result').innerHTML='';};
  const text=$('#settings-import-text'),fileInput=$('#settings-import-file');
  text.oninput=()=>{controller.setText(text.value);reset();};
  fileInput.onchange=async()=>{
    controller.setText('');text.value='';reset();const generation=controller.generation;
    const file=fileInput.files[0];if(!file)return;
    try{
      if(file.size>2*1024*1024)throw Error('File JSON tối đa 2 MiB.');
      const value=await file.text();
      if(!host.isConnected||generation!==controller.generation||fileInput.files[0]!==file)return;
      text.value=value;controller.setText(value);notice('#settings-import-feedback','Đã đọc '+file.name+'. Bấm Kiểm tra & xem trước.');
    }catch(e){if(host.isConnected)notice('#settings-import-feedback',e.message,true);}
  };
  $('#settings-import-check').onclick=e=>busy(e.currentTarget,async()=>{
    controller.setText(text.value);reset();const preview=await controller.check();
    if(!preview||!host.isConnected)return;
    $('#settings-import-result').innerHTML=settingsPreviewMarkup(preview);$('#settings-import-fill').disabled=false;
    notice('#settings-import-feedback','JSON hợp lệ. Chưa điền form, chưa lưu.');
  },'#settings-import-feedback');
  $('#settings-import-fill').onclick=()=>{
    try{controller.apply();$('#settings-import-fill').disabled=true;notice('#settings-import-feedback','Đã điền vào các ô bên dưới. Chưa lưu: bấm Lưu chính sách / Lưu hồ sơ tương ứng sau khi kiểm tra.');}
    catch(e){notice('#settings-import-feedback',e.message,true);}
  };
}
