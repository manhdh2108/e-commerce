// Import state tests with in-memory stubs: no DOM automation or live HTTP.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const requests=[];
const context={requests,editingSaved:()=>false,captureAction:()=>{},captureVersionName:()=>{},configPage:()=>{},toast:()=>{},$:()=>null};
vm.createContext(context);
vm.runInContext(`let versions=[],summarySource='draft',preferredVersion='',configMode='edit',planId='old';\n${fs.readFileSync(path.join(__dirname,'../web/config-transfer.js'),'utf8')}\nthis.getState=()=>({versions,summarySource,preferredVersion,configMode,planId});`,context);
(async()=>{
 await assert.rejects(context.saveImportedConfig(),/kiểm tra file/);
 vm.runInContext(`configImportPreview={payload:{text:'{"config":{}}'}}`,context);
 context.editingSaved=()=>true;
 await assert.rejects(context.saveImportedConfig(),/lưu hoặc hủy/);
 assert.equal(requests.length,0);
 context.editingSaved=()=>false;
 context.api=async(route,method,payload)=>{
  requests.push({route,method,payload});
  if(route==='config-imports')return {id:'new-id',name:'Imported'};
  return [{id:'new-id',name:'Imported',config:{}}];
 };
 await context.saveImportedConfig();
 assert.equal(requests[0].route,'config-imports');assert.equal(requests[0].method,'POST');
 assert.equal(context.getState().summarySource,'new-id');assert.equal(context.getState().planId,'');
 assert.equal(context.getState().preferredVersion,'new-id');
 context.invalidateConfigImport();
 await assert.rejects(context.saveImportedConfig(),/kiểm tra file/);
 console.log('Config transfer checks passed: preview required, unsaved edits protected, new-version POST and stale-plan invalidation.');
})().catch(e=>{console.error(e);process.exitCode=1});
