/* 工作看板 · 离线缓存（网络优先，断网回退缓存）
   ── 2026-11-16 修复 scope 串页 ──
   本 sw 注册在 /work-kanban-board/ 根，scope 天然罩住 /stock-select/ 与 /grid-backtest/
   两个子站。此前断网/弱网时 navigate 回退会把子站请求喂回根首页（工作看板），
   表现就是「打开选股看板，出来的却是工作看板」。
   现改为：子站请求一律不接管，交回浏览器与子站自己的 sw；
   根路径也不再做「兜底回首页」，避免任何跨页串味。 */
var CACHE = 'wb-rt-v12';
var 子站前缀 = ['/work-kanban-board/stock-select/', '/work-kanban-board/grid-backtest/'];

self.addEventListener('install', function(e){ self.skipWaiting(); });
self.addEventListener('activate', function(e){
  e.waitUntil((async function(){
    var names = await caches.keys();
    await Promise.all(names.filter(function(n){ return n !== CACHE; })
      .map(function(n){ return caches.delete(n); }));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', function(ev){
  if (ev.request.method !== 'GET') return;
  var url = ev.request.url;
  if (url.indexOf(self.location.origin) !== 0) return;
  /* 子站让路：不接管，根 sw 绝不参与子站页面与数据 */
  try{
    var p = new URL(url).pathname;
    for (var i = 0; i < 子站前缀.length; i++){
      if (p.indexOf(子站前缀[i]) === 0) return;
    }
  }catch(e){}
  ev.respondWith((async function(){
    try{
      var r = await fetch(ev.request, {cache:'no-store'});
      if (r && r.ok){ var c = await caches.open(CACHE); c.put(ev.request, r.clone()); }
      return r;
    }catch(err){
      var c = await caches.open(CACHE);
      var m = await c.match(ev.request, {ignoreSearch:true});
      if (m) return m;
      throw err;
    }
  })());
});
