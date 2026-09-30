const CACHE='halaqat-shell-22';
const SHELL=['/offline','/static/offline.js','/static/calm.css','/static/manifest.webmanifest','/static/brand-logo.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('halaqat-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
 const u=new URL(e.request.url);
 if(e.request.method!=='GET'||u.origin!==location.origin)return;
 // Never cache authenticated HTML, APIs, passwords or report responses.
 if(SHELL.includes(u.pathname))e.respondWith(fetch(e.request).catch(()=>caches.match(u.pathname)));
});
self.addEventListener('push',e=>{
 let d={};try{d=e.data.json();}catch{}
 e.waitUntil(self.registration.showNotification(d.title||'حلقات مشكاة ونور',{body:d.body||'يوجد تحديث في حسابك',tag:d.tag||'halaqat',icon:'/static/brand-logo.png',data:{url:'/halaqat'}}));
});
self.addEventListener('notificationclick',e=>{e.notification.close();e.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(async windows=>{for(const w of windows){if(new URL(w.url).origin===location.origin){await w.navigate('/halaqat');return w.focus();}}return clients.openWindow('/halaqat');}));});
