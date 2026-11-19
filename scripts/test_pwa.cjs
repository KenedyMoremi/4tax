const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
for (const file of ['static/pwa/sw.js','ussd-emulator/src/main/resources/static/sw.js']) {
  test(file + ' caches only fallback and never intercepts writes or APIs', async () => {
    const handlers = {}, added = [], removed = [];
    const fallback = {offline: true}, online = {online: true};
    let fail = false, fetches = 0;
    const cache = {add: async request => added.push(request.url), match: async () => fallback};
    const context = {
      self: {location: {origin:'https://example.test'}, clients:{claim:async()=>{}}, addEventListener:(name,fn)=>handlers[name]=fn},
      caches: {open:async()=>cache, keys:async()=>['unrelated-cache'], delete:async name=>removed.push(name)},
      Request: class {constructor(url){this.url=url;}},
      Response: {error:()=>({error:true})}, URL,
      fetch:async()=>{fetches++; if(fail)throw Error('offline'); return online;}
    };
    vm.runInNewContext(fs.readFileSync(file,'utf8'), context);
    let pending;
    handlers.install({waitUntil:p=>pending=p}); await pending;
    assert.equal(added.length,1); assert.ok(added[0].endsWith('/offline.html'));
    handlers.activate({waitUntil:p=>pending=p}); await pending;
    assert.deepEqual(removed,[]);
    async function request(method,mode,url) {
      let response;
      handlers.fetch({request:{method,mode,url},respondWith:p=>response=p});
      return response === undefined ? undefined : await response;
    }
    for(const path of ['/pos/','/accounts/login/','/book/','/api/private']) {
      assert.equal(await request('POST','navigate','https://example.test'+path),undefined);
      assert.equal(await request('GET','cors','https://example.test'+path),undefined);
    }
    assert.equal(await request('GET','navigate','https://other.test/'),undefined);
    assert.equal(fetches,0);
    assert.equal(await request('GET','navigate','https://example.test/pos/'),online);
    fail=true;
    assert.equal(await request('GET','navigate','https://example.test/pos/'),fallback);
    assert.equal(added.length,1);
  });
}
