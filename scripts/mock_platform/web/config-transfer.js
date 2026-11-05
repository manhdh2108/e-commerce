/* File imports are previewed first and always saved as a new configuration. */
let configImportText='',configImportPreview=null,configImportGeneration=0;
function invalidateConfigImport(){
  configImportGeneration++;
  configImportPreview=null;
  if($('#import-save'))$('#import-save').disabled=true;
  if($('#import-result'))$('#import-result').innerHTML='';
}
function mountConfigTransfer(){
  configImportText='';configImportPreview=null;configImportGeneration++;
  $('#main .config-switches').insertAdjacentHTML('afterend',`<details class="card config-transfer"><summary>Nhập / Xuất cấu hình JSON</summary><p>Chọn file, kiểm tra rồi lưu thành cấu hình mới. Cấu hình đang có và dữ liệu OLTP được giữ nguyên.</p><div class="actions"><a class="btn secondary small" href="/api/config-template-v2" download>Tải mẫu mới: hành trình liên kết 2026</a><a class="btn secondary small" href="/api/config-template" download>Mẫu cũ: đặt trực tiếp</a><button class="btn secondary small" id="export-config">Xuất cấu hình đang xem</button></div><div class="formgrid" style="margin-top:16px"><div class="field"><label for="import-file">File JSON (tối đa 2 MiB)</label><input id="import-file" type="file" accept=".json,application/json"></div>${field('Tên cấu hình mới (trống: dùng tên trong file)','import-name','')}</div>${editingSaved()?'<div class="notice">Bạn còn cấu hình đang chỉnh sửa. Hãy lưu hoặc hủy chỉnh sửa trước khi lưu cấu hình nhập.</div>':''}<div class="actions"><button class="btn secondary" id="import-preview">Kiểm tra & xem trước</button><button class="btn" id="import-save" disabled>Lưu thành cấu hình mới</button></div><div id="import-feedback"></div><div id="import-result"></div></details>`);
  $('#import-file').onchange=async()=>{
    invalidateConfigImport();configImportText='';
    const file=$('#import-file').files[0];if(!file)return;
    try{
      if(file.size>2*1024*1024)throw Error('File JSON tối đa 2 MiB.');
      const text=await file.text();
      if(!$('#import-file')||$('#import-file').files[0]!==file)return;
      configImportText=text;notice('#import-feedback','Đã đọc file '+file.name+'. Bấm Kiểm tra & xem trước.');
    }catch(error){notice('#import-feedback',error.message,true)}
  };
  $('#import-name').oninput=invalidateConfigImport;
  $('#import-preview').onclick=e=>busy(e.currentTarget,async()=>{
    invalidateConfigImport();
    if(!configImportText)throw Error('Hãy chọn file JSON trước.');
    const generation=configImportGeneration;
    const text=configImportText,name=$('#import-name').value.trim();
    const payload={text};if(name)payload.name=name;
    const preview=await api('config-imports/preview','POST',payload);
    if(generation!==configImportGeneration||!$('#import-result'))return;
    configImportPreview={preview,payload};
    $('#import-result').innerHTML=`<h3>${esc(preview.name)}</h3><p>${preview.summary.enabled} hành động bật · ${preview.summary.automatic} hành động xử lý theo đầu vào.</p>${preview.warnings.map(w=>`<div class="notice">${esc(w)}</div>`).join('')}<details><summary>Xem hành động và lịch của cả 6 hệ thống</summary>${P.summary(catalog,preview.config)}</details>`;
    $('#import-save').disabled=editingSaved();
    notice('#import-feedback','File hợp lệ. Chưa lưu cấu hình và chưa chạy dữ liệu.');
  },'#import-feedback');
  $('#import-save').onclick=e=>busy(e.currentTarget,saveImportedConfig,'#import-feedback');
  $('#export-config').onclick=()=>{
    captureAction();captureVersionName();
    const saved=versions.find(v=>v.id===summarySource);
    const config=editingSaved()?editingConfig:saved?saved.config:draft;
    const name=editingSaved()?versionName:saved?saved.name:versionName||'Bản nháp';
    const blob=new Blob([JSON.stringify({format:'mock-studio-config',format_version:Object.values(config).some(c=>c.variants?.length)?2:1,name,config},null,2)],{type:'application/json'});
    const link=document.createElement('a'),url=URL.createObjectURL(blob);
    link.href=url;link.download='mock-studio-config.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
}
async function saveImportedConfig(){
  if(editingSaved())throw Error('Hãy lưu hoặc hủy cấu hình đang chỉnh sửa trước.');
  if(!configImportPreview)throw Error('Hãy kiểm tra file trước khi lưu.');
  captureAction();captureVersionName();
  const payload=configImportPreview.payload;
  const saved=await api('config-imports','POST',payload);
  versions=await api('versions');
  summarySource=saved.id;preferredVersion=saved.id;configMode='summary';planId='';
  configPage();toast('Đã nhập “'+saved.name+'”. Chưa chạy mô phỏng.');
}
