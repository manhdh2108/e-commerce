// Pure presentation tests: no browser, database writes, or simulation jobs.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const P=require('../web/presentation.js');
const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../resources/actions.json'),'utf8'));
const config={
 'CUS-05':{enabled:true,count:8,params:{method:'Momo',quantity:1,channel:'App'},special:{'2026-11-11':24}},
 'PAY-01':{enabled:true,count:0,mode:'all',params:{success_rate:100},special:{}},
 'FIN-POL-01':{enabled:true,count:0,params:{category:9423,tier:'Normal',rate:5,start:'2026-01-01'},special:{'2026-01-01':1}},
 'SEL-01':{enabled:false,count:1,params:{value:'<script>alert(1)</script>'}},
};
const before=JSON.stringify(config);
const summary=P.summary(catalog,config);
assert(summary.includes('Đặt hàng sau khi đăng nhập'));
assert(summary.includes('24 lần'));
assert(summary.includes('11/11/2026'));
assert(summary.includes('Tự xử lý khi có yêu cầu đủ điều kiện'));
assert(summary.includes('Ví MoMo'));
assert(summary.includes('Sản phẩm &amp; Người bán'));
assert(summary.includes('Hành vi truy cập'));
assert(summary.includes('5%'));
assert(summary.includes('01/01/2026: 1 lần'));
assert.equal((summary.match(/class="card scenario-system"/g)||[]).length,6);
assert.equal(JSON.stringify(config),before,'Reading a summary must not mutate configuration');
const visible=summary.replace(/<details class="technical">[\s\S]*?<\/details>/g,'');
assert(!visible.includes('CUS-05'));
assert(!visible.includes('PAY-01'));
assert(!visible.includes('<script>'));
assert(!summary.includes('ALL_REQUESTS'));
const plan=P.plan(catalog,{days:[{day:'2026-11-11',total:24,automatic:1,actions:[{code:'CUS-05',system:'orders',requested:24},{code:'PAY-01',system:'orders',requested:'Theo đầu vào'}]}]});
assert(plan.includes('Khách đã đăng ký'));
assert(plan.includes('Đặt hàng sau khi đăng nhập'));
assert(plan.includes('24 lần'));
assert(plan.includes('Trả kết quả thanh toán trả trước'));
assert(!plan.replace(/<details class="technical">[\s\S]*?<\/details>/g,'').includes('CUS-05'));
assert.equal(P.message(catalog,'CUS-05 · Đặt hàng sau khi đăng nhập'),'Đặt hàng sau khi đăng nhập');
assert.equal(P.message(catalog,'FIN-SEL-01 · Xem đối soát của shop'),'Xem đối soát của shop');
assert(!P.message(catalog,'CUS-05: không đủ dữ liệu').includes('CUS-05'));
assert(P.message(catalog,'Không có đối tượng hợp lệ trong inventory_levels.').includes('tồn kho'));
assert(P.summary(catalog,{}).includes('Chưa bật hành động'));
const injection={'SEL-01':{enabled:true,count:1,params:{value:'<img src=x onerror=alert(1)>'},special:{}}};
assert(!P.summary(catalog,injection).includes('<img'));
console.log('Presentation checks passed: 6-system overview, saved configuration semantics, Vietnamese labels, quotas, dates, auto mode, escaping and no mutation.');
