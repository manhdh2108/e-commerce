// Settings fill controller: preview required, stale response rejected, no auto-save.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const P=require('../web/presentation.js'),context={esc:P.esc};vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/settings-transfer.js'),'utf8'),context);
const Controller=vm.runInContext('SettingsImportController',context);
(async()=>{
 const filled=[],calls=[];
 const policy={return_window_days:7,payout_hold_days:10,max_delivery_attempts:3};
 const preview={name:'<script>x</script>',business_policy:policy,summary:{},warnings:['<unsafe>']};
 const ctrl=new Controller(p=>filled.push(p),async payload=>{calls.push(payload);return preview});
 assert.throws(()=>ctrl.apply(),/kiểm tra JSON/);
 ctrl.setText('first');await ctrl.check();assert.equal(filled.length,0);
 ctrl.apply();assert.equal(filled.length,1);assert.deepEqual(JSON.parse(JSON.stringify(filled[0].business_policy)),policy);
 filled[0].business_policy.return_window_days=99;assert.equal(preview.business_policy.return_window_days,7,'Filling cannot mutate validated preview');
 assert.throws(()=>ctrl.apply(),/kiểm tra JSON/);
 let complete;ctrl.request=()=>new Promise(resolve=>complete=resolve);
 ctrl.setText('old');const pending=ctrl.check();ctrl.setText('new');complete(preview);
 assert.equal(await pending,null);assert.throws(()=>ctrl.apply(),/kiểm tra JSON/);
 const html=context.settingsPreviewMarkup(preview);
 assert(html.includes('&lt;script&gt;'));assert(!html.includes('<script>x'));
 assert(html.includes('Không thay đổi các ô hồ sơ'));assert(html.includes('Giữ tiền trước đối soát'));
 assert(calls.length===1,'No implicit save call');
 console.log('Settings import checks passed: preview/fill separation, copy isolation, stale responses and safe readable summary.');
})().catch(e=>{console.error(e);process.exitCode=1});
