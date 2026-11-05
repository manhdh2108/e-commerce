// Isolated state-machine tests. No DOM/browser access or real HTTP requests.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const getcfg=source.slice(source.indexOf('function getcfg('),source.indexOf('function configEditor('));
const functions=source.slice(source.indexOf('function captureVersionName()'),source.indexOf('function configPage()'));
const requests=[];
const context={console,requests,$:()=>null,captureAction:()=>{},configPage:()=>{},toast:()=>{},notice:()=>{},busy:()=>{},esc:x=>String(x)};
vm.createContext(context);
vm.runInContext(`let draft={A:{count:3}},versions=[{id:'saved-one',name:'Cấu hình A',revision:4,config:{A:{count:1}}}],editingVersionId='',editingRevision=null,editingConfig=null,versionName='Tên bản nháp',previousDraftName='',summarySource='draft',configMode='summary',planId='old-preview';\n${getcfg}\n${functions}\nthis.inspectState=()=>({draft,versions,editingVersionId,editingRevision,editingConfig,versionName,summarySource,planId});`,context);
context.api=async(path,method,payload)=>{
 requests.push({path,method,payload:payload&&JSON.parse(JSON.stringify(payload))});
 if(method==='PUT')return {changed:true,revision:5,id:'saved-one'};
 return [{id:'saved-one',name:'Cấu hình A',revision:5,config:{A:{count:9}}}];
};
(async()=>{
 context.beginSavedEdit('saved-one');
 assert.equal(context.inspectState().editingRevision,4);
 vm.runInContext("getcfg('A').count=9",context);
 assert.equal(context.inspectState().draft.A.count,3);
 assert.equal(context.inspectState().versions[0].config.A.count,1,'Editing must not mutate the loaded saved record');
 await context.saveSavedChanges();
 assert.equal(requests[0].path,'versions/saved-one');
 assert.equal(requests[0].method,'PUT');
 assert.equal(requests[0].payload.revision,4);
 assert.equal(requests[0].payload.config.A.count,9);
 assert.equal(context.inspectState().summarySource,'saved-one');
 assert.equal(context.inspectState().planId,'');
 assert.equal(context.inspectState().draft.A.count,3);
 context.beginSavedEdit('saved-one');
 vm.runInContext("getcfg('A').count=25",context);
 context.api=async()=>{throw Error('conflict')};
 await assert.rejects(context.saveSavedChanges(),/conflict/);
 assert.equal(context.inspectState().editingConfig.A.count,25,'Conflict must preserve local edits');
 context.cancelSavedEdit();
 assert.equal(context.inspectState().editingVersionId,'');
 assert.equal(context.inspectState().draft.A.count,3,'Cancel must not overwrite draft');
 console.log('Saved-config editor checks passed: same-ID PUT, clone isolation, revision token, cancellation, stale-plan clearing and conflict preservation.');
})().catch(e=>{console.error(e);process.exitCode=1});
