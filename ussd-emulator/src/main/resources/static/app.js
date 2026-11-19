import {trafficEntries, trafficPayload} from './traffic.js';
const $ = id => document.getElementById(id);
const storageKey = 'fourtax-emulator-subscribers-v1';
let subscribers = [], selectedId, config, tab = 'request';
const sessions = new Map();
const uuid = () => crypto.randomUUID();
const state = id => {
  if (!sessions.has(id)) sessions.set(id, {active:false,busy:false,traces:[],selected:-1,step:0,lastActivity:0});
  return sessions.get(id);
};
const current = () => subscribers.find(s => s.id === selectedId);
function notice(message) { $('notice').textContent = message || ''; $('notice').hidden = !message; }
function saveSubscribers() {
  try { localStorage.setItem(storageKey, JSON.stringify(subscribers)); } catch { /* Storage is optional. */ }
}
async function api(path, data) {
  const response = await fetch('/api/emulator/' + path, data === undefined ? {} : {
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || 'The emulator could not complete this request.');
  return result;
}
async function generate(count) {
  if (subscribers.length + count > 50) return notice('Keep up to 50 subscribers in this workspace. Remove a profile to add another.');
  $('generate-one').disabled = $('generate-five').disabled = true;
  try {
    const generated = await api('identities', {count,prefix:$('number-prefix').value,mnc:$('mnc').value});
    const numbers = new Set(subscribers.map(s => s.mobileNumber)), imsis = new Set(subscribers.map(s => s.imsi));
    for (const subscriber of generated) {
      if (numbers.has(subscriber.mobileNumber) || imsis.has(subscriber.imsi)) continue;
      subscriber.label = 'Subscriber ' + (subscribers.length + 1);
      subscribers.push(subscriber); numbers.add(subscriber.mobileNumber); imsis.add(subscriber.imsi);
      selectedId = subscriber.id;
    }
    notice(''); saveSubscribers(); render();
  } catch (error) { notice(error.message); }
  finally { $('generate-one').disabled = $('generate-five').disabled = false; }
}
function renderSubscribers() {
  $('subscriber-count').textContent = subscribers.length;
  $('subscribers').replaceChildren();
  for (const subscriber of subscribers) {
    const s = state(subscriber.id);
    const button = document.createElement('button'); button.type = 'button';
    button.className = 'subscriber' + (selectedId === subscriber.id ? ' selected' : '');
    button.setAttribute('aria-pressed', String(selectedId === subscriber.id));
    const icon = document.createElement('span'); icon.className = 'subscriber-icon'; icon.textContent = 'S'; icon.setAttribute('aria-hidden','true');
    const text = document.createElement('span'); text.className = 'subscriber-text';
    const label = document.createElement('strong'); label.textContent = subscriber.label;
    const number = document.createElement('span'); number.textContent = subscriber.mobileNumber;
    text.append(label, number);
    const status = document.createElement('span'); status.className = 'subscriber-status' + (s.active ? ' active' : '');
    status.textContent = s.busy ? 'BUSY' : s.active ? 'IN CALL' : 'READY';
    button.append(icon,text,status); button.onclick = () => { selectedId = subscriber.id; notice(''); render(); };
    $('subscribers').append(button);
  }
}
function render() {
  renderSubscribers();
  const subscriber = current(); if (!subscriber) return;
  const s = state(selectedId);
  $('identity-msisdn').textContent = subscriber.mobileNumber;
  $('identity-imsi').textContent = subscriber.imsi;
  $('identity-network').replaceChildren(document.createTextNode('Vodacom Lesotho '));
  const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = subscriber.mcc + ' / ' + subscriber.mnc;
  $('identity-network').append(tag);
  $('identity-session').textContent = s.sessionId || 'Starts when you dial';
  $('screen-code').textContent = s.connection?.serviceCode || $('service-code').value;
  $('screen-step').textContent = s.step ? 'STEP ' + s.step : 'USSD';
  if (s.prompt !== undefined) $('ussd-screen').textContent = s.prompt;
  else {
    $('ussd-screen').replaceChildren();
    const empty = document.createElement('div'); empty.className = 'empty-screen';
    const symbol = document.createElement('span'); symbol.className = 'empty-symbol'; symbol.textContent = '*#';
    const title = document.createElement('strong'); title.append('A small screen.',document.createElement('br'),'A complete journey.');
    const hint = document.createElement('p'); hint.textContent = 'Choose a subscriber and dial your service to begin.';
    empty.append(symbol,title,hint); $('ussd-screen').append(empty);
  }
  const usable = s.active && !s.busy && !s.uncertain;
  $('reply-input').disabled = $('send-reply').disabled = !usable;
  $('reply-input').type = /\bpin\b/i.test(s.prompt || '') ? 'password' : 'text';
  $('reply-input').inputMode = /\bpin\b/i.test(s.prompt || '') ? 'numeric' : 'text';
  $('reply-input').value = s.reply || '';
  $('dial').disabled = s.active || s.busy;
  $('dial').textContent = s.active ? 'Call in progress' : s.step ? 'Dial again' : 'Dial service';
  $('abort').disabled = $('timeout').disabled = !s.active || s.busy;
  $('edit-subscriber').disabled = s.active || s.busy;
  document.querySelectorAll('[data-key]').forEach(button => { button.disabled = !usable; });
  $('call-status').textContent = s.busy ? 'WAITING FOR CALLBACK' : s.uncertain ? 'CALLBACK NEEDS ATTENTION' : s.active ? 'SESSION CONNECTED' : s.step ? 'SESSION ENDED' : 'READY TO DIAL';
  $('call-status').className = 'call-status' + (s.uncertain ? ' failed' : s.active ? ' active' : '');
  renderTraffic(); updateClock();
}
function renderTraffic() {
  const s = state(selectedId);
  const entries = trafficEntries(s.traces);
  $('exchange-count').textContent = s.traces.length + ' callbacks · ' + (entries.length - s.traces.length) + ' API checks';
  const latest = s.traces.at(-1);
  $('last-latency').textContent = latest ? latest.result.durationMs + ' ms' : 'Waiting for a call';
  $('traffic-list').replaceChildren();
  if (!s.traces.length) {
    const empty = document.createElement('p'); empty.className = 'empty-traffic';
    empty.append('Each screen is a callback.',document.createElement('br'),'Your requests and responses appear here.'); $('traffic-list').append(empty);
  }
  entries.forEach(({index,apiIndex,label,status:code,durationMs,failed}) => {
    const button = document.createElement('button'); button.className = 'traffic-row' + (apiIndex == null ? '' : ' traffic-api-row')
      + (index === s.selected && apiIndex == s.selectedApi ? ' selected' : ''); button.type = 'button';
    const number = document.createElement('span'); number.className = 'traffic-index'; number.textContent = String(index + 1).padStart(2,'0');
    if (apiIndex != null) number.textContent = '↳';
    const event = document.createElement('span'); event.className = 'traffic-event'; event.textContent = label;
    const status = document.createElement('span'); status.className = 'traffic-code' + (failed ? ' failed' : '');
    status.textContent = code + ' · ' + durationMs + ' ms';
    button.append(number,event,status); button.onclick = () => { s.selected = index; s.selectedApi = apiIndex; renderTraffic(); }; $('traffic-list').append(button);
  });
  const trace = s.traces[s.selected];
  const call = s.selectedApi == null ? null : trace?.result.backendExchanges?.[s.selectedApi];
  $('payload').textContent = trafficPayload(trace,tab,s.selectedApi,$('reveal-input').checked);
  $('copy-payload').disabled = !trace;
  $('replay').disabled = !s.lastRequest || s.busy;
  $('payload-info').textContent = call ? 'JSON · ' + (tab === 'request' ? call.method : call.outcome)
    : trace ? 'XML · ' + (tab === 'request' ? 'POST' : 'HTTP ' + trace.result.httpStatus) : 'XML · UTF-8';
  $('exchange-error').textContent = trace?.result.errorMessage || '';
  $('exchange-error').hidden = !trace?.result.errorMessage;
  for (const button of document.querySelectorAll('[data-tab]')) button.setAttribute('aria-selected', String(button.dataset.tab === tab));
  if (trace?.result.effectiveUrl && trace.result.effectiveUrl !== trace.result.callbackUrl)
    $('payload-info').title = 'Server destination: ' + trace.result.effectiveUrl;
  else $('payload-info').removeAttribute('title');
}
function connection() {
  return {callbackUrl:$('callback-url').value.trim(),gatewayHeader:$('gateway-header').value.trim(),gatewayKey:$('gateway-key').value,
    serviceCode:$('service-code').value.trim(),numberFormat:$('number-format').value,includeRequestId:$('include-request-id').checked,
    timeoutSeconds:Number($('request-timeout').value),idleTimeout:Number($('idle-timeout').value),inspectBackend:$('inspect-backend').checked};
}
async function exchange(id, event, input = '', replay = false) {
  const subscriber = subscribers.find(item => item.id === id); if (!subscriber) return;
  const s = state(id); if (s.busy) return;
  notice('');
  let request;
  const sensitive = replay ? s.lastSensitive : /\bpin\b/i.test(s.prompt || '');
  if (replay) {
    if (!s.lastRequest) return;
    request = {...s.lastRequest};
    if ($('callback-url').value.trim() === request.callbackUrl) {
      request.gatewayKey = $('gateway-key').value; request.gatewayHeader = $('gateway-header').value.trim();
    }
  } else {
    if (event === 'START') {
      if (s.active) return;
      s.connection = connection(); s.subscriber = {...subscriber}; s.sessionId = uuid(); s.step = 0;
      s.active = true; s.uncertain = false; s.prompt = 'Connecting to your service…'; s.reply = '';
    }
    if (!s.connection || !s.sessionId) return;
    request = {...s.connection,subscriber:s.subscriber,sessionId:s.sessionId,requestId:uuid(),event,input,timestamp:new Date().toISOString()};
  }
  s.busy = true; s.lastActivity = Date.now();
  s.lastRequest = request; s.lastSensitive = sensitive;
  if (id === selectedId) render(); else renderSubscribers();
  try {
    const result = await api('exchanges',request);
    s.lastRequest = request; s.lastSensitive = sensitive;
    s.traces.push({result,sensitive,replay});
    if (s.traces.length > 100) s.traces.shift();
    s.selected = s.traces.length - 1;
    const failure = (result.backendExchanges || []).findIndex(call => !['OK','VERIFIED'].includes(call.outcome));
    s.selectedApi = failure < 0 ? null : failure;
    if (failure >= 0) tab = 'response';
    if (result.errorCode) {
      s.uncertain = true;
      s.prompt = result.errorMessage + '\n\nUse Replay request to retry this exchange.';
    } else {
      s.uncertain = false; s.prompt = result.prompt; s.active = result.state === 'NextState';
      if (!replay) s.step++;
      s.reply = '';
    }
    if (event === 'ABORT' || event === 'TIMEOUT' || request.event === 'ABORT' || request.event === 'TIMEOUT') {
      s.active = false; s.uncertain = false;
      if (result.errorCode) s.prompt = 'Call ended locally. The callback could not confirm the abort.\n\n' + result.errorMessage;
    }
    s.lastActivity = Date.now();
  } catch (error) {
    s.uncertain = true; s.prompt = error.message;
    if (event === 'START') { s.active = false; s.uncertain = false; }
    if (event === 'ABORT' || event === 'TIMEOUT') { s.active = false; s.uncertain = false; }
    notice(error.message);
  } finally {
    s.busy = false;
    if (id === selectedId) { render(); if (s.active && !s.uncertain) $('reply-input').focus(); }
    else renderSubscribers();
  }
}
function updateClock() {
  if (!selectedId) return;
  const s = state(selectedId), seconds = s.connection?.idleTimeout;
  if (!s.active || !seconds || s.busy) { $('idle-clock').textContent = ''; return; }
  const remaining = Math.max(0,seconds - Math.floor((Date.now()-s.lastActivity)/1000));
  $('idle-clock').textContent = Math.floor(remaining/60) + ':' + String(remaining%60).padStart(2,'0') + ' idle';
}
$('reply-form').onsubmit = event => {
  event.preventDefault(); const s = state(selectedId);
  if (s.active && !s.busy && !s.uncertain && $('reply-input').value.length)
    exchange(selectedId,'INPUT',$('reply-input').value);
};
$('reply-input').oninput = () => { state(selectedId).reply = $('reply-input').value; };
$('dial').onclick = () => exchange(selectedId,'START');
$('abort').onclick = () => exchange(selectedId,'ABORT');
$('timeout').onclick = () => exchange(selectedId,'TIMEOUT');
$('replay').onclick = () => exchange(selectedId,state(selectedId).lastRequest?.event,'',true);
$('generate-one').onclick = () => generate(1);
$('generate-five').onclick = () => generate(5);
$('service-code').oninput = () => { if (!state(selectedId).active) $('screen-code').textContent = $('service-code').value; };
$('toggle-key').onclick = () => {
  const reveal = $('gateway-key').type === 'password'; $('gateway-key').type = reveal ? 'text' : 'password';
  $('toggle-key').textContent = reveal ? 'Hide' : 'Show'; $('toggle-key').setAttribute('aria-label', reveal ? 'Hide gateway key' : 'Show gateway key');
};
document.querySelectorAll('[data-key]').forEach(button => { button.onclick = () => {
  if ($('reply-input').value.length < 256) $('reply-input').value += button.dataset.key;
  state(selectedId).reply = $('reply-input').value; $('reply-input').focus();
}; });
document.querySelectorAll('[data-tab]').forEach(button => { button.onclick = () => { tab = button.dataset.tab; renderTraffic(); }; });
$('reveal-input').onchange = renderTraffic;
$('copy-payload').onclick = async () => {
  try { await navigator.clipboard.writeText($('payload').textContent); $('copy-payload').textContent = 'Copied'; setTimeout(() => { $('copy-payload').textContent = 'Copy'; },1500); }
  catch { notice('Clipboard unavailable. Select and copy the payload text.'); }
};
$('clear-traffic').onclick = () => { const s=state(selectedId); s.traces=[]; s.selected=-1; renderTraffic(); };
$('edit-subscriber').onclick = () => {
  const subscriber=current(); if (!subscriber || state(selectedId).active) return;
  $('edit-label').value=subscriber.label; $('edit-mobile').value=subscriber.mobileNumber; $('edit-imsi').value=subscriber.imsi;
  $('delete-subscriber').disabled=subscribers.length===1; $('identity-dialog').showModal();
};
$('close-dialog').onclick = () => $('identity-dialog').close();
$('identity-form').onsubmit = event => {
  event.preventDefault(); const subscriber=current();
  let mobile=$('edit-mobile').value.replace(/[ +()-]/g,''); if (/^5\d{7}$/.test(mobile)) mobile='266'+mobile;
  const imsi=$('edit-imsi').value;
  if (!/^2665\d{7}$/.test(mobile) || !/^651(?:01|10)\d{10}$/.test(imsi)) return notice('Use a Lesotho 5-series number and a 15-digit IMSI beginning with 65101 or 65110.');
  if (subscribers.some(item => item.id!==selectedId && (item.mobileNumber==='+'+mobile || item.imsi===imsi))) return notice('That number or IMSI already belongs to another test subscriber.');
  subscriber.label=$('edit-label').value.trim() || subscriber.label; subscriber.mobileNumber='+'+mobile;
  subscriber.imsi=imsi; subscriber.mnc=imsi.substring(3,5);
  sessions.delete(selectedId); saveSubscribers(); $('identity-dialog').close(); notice(''); render();
};
$('delete-subscriber').onclick = () => {
  if (subscribers.length<2 || state(selectedId).active) return;
  sessions.delete(selectedId); subscribers=subscribers.filter(item=>item.id!==selectedId); selectedId=subscribers[0].id;
  saveSubscribers(); $('identity-dialog').close(); render();
};
setInterval(() => {
  updateClock();
  for (const [id,s] of sessions) if (s.active && !s.busy && !s.uncertain && s.connection?.idleTimeout>0
    && Date.now()-s.lastActivity>=s.connection.idleTimeout*1000) exchange(id,'TIMEOUT');
},1000);
try {
  config=await api('config'); $('callback-url').value=config.callbackUrl; $('service-code').value=config.serviceCode;
  try {
    const stored=JSON.parse(localStorage.getItem(storageKey)||'[]');
    if (Array.isArray(stored)) subscribers=stored.filter(s=>s && typeof s.id==='string' && typeof s.label==='string'
      && /^\+2665\d{7}$/.test(s.mobileNumber) && /^651(?:01|10)\d{10}$/.test(s.imsi) && s.network==='VOD').slice(0,50);
  } catch { /* Start with a new synthetic identity. */ }
  if (subscribers.length) { selectedId=subscribers[0].id; render(); } else await generate(1);
} catch (error) { notice('Could not load the emulator: '+error.message); }
