// Pure form and presentation checks, without browser/network access.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const P=require('../web/presentation.js');
const context={P,esc:P.esc,getcfg:()=>({params:{}})};vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/profiles.js'),'utf8'),context);
const action={code:'GST-WEB-01',fields:[{key:'device',label:'Thiết bị',type:'select',options:['Mobile','Desktop'],default:'Mobile'},{key:'quantity',label:'Số lượng',type:'number',min:1,default:1}]};
const markup=context.profileRow(action,{name:'<script>bad</script>',weight:7,params:{device:'Desktop',quantity:2}});
assert(!markup.includes('<script>bad'));
assert(markup.includes('&lt;script&gt;'));
assert(markup.includes('Máy tính'));
assert(markup.includes('Trọng số (không phải số lượt)'));
const numeric={dataset:{profileParam:'quantity'},type:'number',value:'2'},device={dataset:{profileParam:'device'},type:'select',value:'Desktop'};
const fakeRow={querySelector:selector=>selector==='[data-profile-name]'?{value:'Máy tính'}:{value:'3'},querySelectorAll:()=>[numeric,device]};
context.$=selector=>selector==='#profile-rows'?{}:selector==='#action-delay'?{value:'2'}:null;
context.document={querySelectorAll:()=>[fakeRow]};
const cfg={};context.captureActionProfiles(cfg);
assert.equal(cfg.delay_days,2);assert.equal(cfg.variants[0].weight,3);assert.equal(cfg.variants[0].params.quantity,2);
context.document.querySelectorAll=()=>[];context.captureActionProfiles(cfg);assert(!('variants' in cfg));
const summary=P.parameters(action,{params:{device:'Mobile'},variants:[{name:'Máy tính',weight:3,params:{device:'Desktop'}}],delay_days:2});
assert(summary.some(p=>p.label==='Nhóm Máy tính'&&p.value.includes('Máy tính')));
assert(summary.some(p=>p.label==='Độ trễ tối thiểu'&&p.value==='2 ngày'));
console.log('Profile form checks passed: escaping, Vietnamese labels, weighted bundles, numeric capture, removal and delay summary.');

// Editing weighted windows must preserve duration and the advanced execution contract.
const advanced={phase:4,variant_mode:'cycle',preferences:{products:{source:'session_views',weight:8}},schedule:{windows:[{start:'18:00:00',end:'21:00:00',weight:3}],after_seconds:{kind:'integer',min:60,max:600}}};
const fields={'#action-actor-pool':'customers','#action-selection':'{}','#action-parameter-rules':'[]','#schedule-start':'','#schedule-end':'','#schedule-offset':'','#session-duration':'{"kind":"integer","min":600,"max":1800}','#action-runtime-options':JSON.stringify(advanced)};
context.$=selector=>Object.hasOwn(fields,selector)?{value:fields[selector]}:null;
const edited={};context.captureActionProfiles(edited);
assert.equal(edited.phase,4);assert.equal(edited.variant_mode,'cycle');assert.equal(edited.preferences.products.source,'session_views');
assert.equal(edited.schedule.windows[0].weight,3);assert.equal(edited.schedule.duration_seconds.max,1800);assert.equal(edited.schedule.after_seconds.min,60);
