// Pure rendering checks: no browser, DOM automation or live HTTP.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');
const context={esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt:n=>Number(n||0).toLocaleString('vi-VN')};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/dashboard.js'),'utf8'),context);
assert.match(context.metricCards([['<img>',42,'<script>']]),/&lt;img&gt;/);
assert.doesNotMatch(context.metricCards([['<img>',42,'<script>']]),/<script>/);
const status=context.statusBars('Đơn hàng',[{status:'Completed',count:3},{status:'Cancelled',count:1}]);
assert.match(status,/Hoàn tất/);assert.match(status,/Đã hủy/);assert.match(status,/max="4"/);
const bars=context.dailyOrderChart([{day:'2026-01-01',orders:10},{day:'2026-01-02',orders:20}]);
assert.match(bars,/height:65px/);assert.match(bars,/height:130px/);assert.match(bars,/01-02/);
assert.match(context.dailyOrderChart([]),/Chưa có đơn hàng/);
const index=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
assert.ok(index.indexOf('/static/dashboard.js')<index.indexOf('/static/app.js'));
console.log('Dashboard rendering checks passed: Vietnamese status names, safe text, proportional chart, empty state and script order.');
