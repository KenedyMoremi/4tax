const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const file = require('node:path').join(__dirname, '../src/main/resources/static/traffic.js');
const loaded = import('data:text/javascript;base64,' + fs.readFileSync(file).toString('base64'));
test('history preserves both sides of every callback and its downstream calls', async () => {
 const {trafficEntries,trafficPayload} = await loaded;
 const traces = [{result:{event:'INPUT',httpStatus:200,durationMs:15,requestXml:'<value>1</value>',responseXml:'first',backendExchanges:[]}},
  {result:{event:'INPUT',httpStatus:200,durationMs:20,requestXml:'<value>001234</value>',responseXml:'second',backendExchanges:[
   {stage:'application-token',method:'POST',url:'https://auth.test/oauth2/token',httpStatus:401,durationMs:19,
    requestHeaders:{Authorization:'[redacted]'},requestBody:{grant_type:'client_credentials'},responseBody:{code:'invalid_client'},outcome:'HTTP_ERROR'}]},sensitive:true}];
 const rows = trafficEntries(traces);
 assert.equal(rows.length,3); assert.equal(rows[2].apiIndex,0); assert.equal(rows[2].failed,true);
 assert.equal(trafficPayload(traces[0],'response'),'first');
 assert.equal(trafficPayload(traces[1],'response'),'second');
 assert.equal(trafficPayload(traces[1],'request'),'<value>[PIN hidden]</value>');
 const request = JSON.parse(trafficPayload(traces[1],'request',0));
 const response = JSON.parse(trafficPayload(traces[1],'response',0));
 assert.equal(request.url,'https://auth.test/oauth2/token'); assert.equal(request.headers.Authorization,'[redacted]');
 assert.equal(response.httpStatus,401); assert.equal(response.body.code,'invalid_client');
});
test('replay and local JWT validation are distinct from new HTTP calls', async () => {
 const {trafficEntries,trafficPayload} = await loaded;
 const trace = {result:{event:'INPUT',httpStatus:200,durationMs:1,backendExchanges:[{stage:'verify-owner-token',method:'LOCAL',httpStatus:0,durationMs:0,outcome:'VERIFIED'}]},replay:true};
 const rows = trafficEntries([trace]);
 assert.match(rows[0].label,/REPLAY/); assert.equal(rows[1].status,'LOCAL'); assert.equal(rows[1].failed,false);
 assert.equal(trafficPayload(null,'request'),'No exchange selected.');
});
