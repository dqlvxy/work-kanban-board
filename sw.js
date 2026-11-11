/* 工作看板 · 离线缓存（网络优先，断网回退缓存） */
var CACHE = 'wb-rt-v8';
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
  ev.respondWith((async function(){
    try{
      var r = await fetch(ev.request, {cache:'no-store'});
      if (r && r.ok){ var c = await caches.open(CACHE); c.put(ev.request, r.clone()); }
      return r;
    }catch(err){
      var c = await caches.open(CACHE);
      var m = await c.match(ev.request, {ignoreSearch:true});
      if (m) return m;
      if (ev.request.mode === 'navigate'){
        var home = await c.match(self.registration.scope, {ignoreSearch:true});
        if (home) return home;
      }
      throw err;
    }
  })());
});
