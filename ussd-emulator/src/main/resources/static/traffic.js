// History stays in tab memory. Payload rendering uses textContent in the workbench.
export function trafficEntries(traces) {
  return traces.flatMap((trace, index) => [
    {index, apiIndex: null, label: trace.result.event + (trace.replay ? ' · REPLAY' : ''),
      status: trace.result.httpStatus || 'ERR', durationMs: trace.result.durationMs, failed: !!trace.result.errorCode},
    ...(trace.result.backendExchanges || []).map((call, apiIndex) => ({index, apiIndex,
      label: call.stage, status: call.method === 'LOCAL' ? 'LOCAL' : call.httpStatus || 'ERR', durationMs: call.durationMs,
      failed: !['OK', 'VERIFIED'].includes(call.outcome)}))
  ]);
}
export function trafficPayload(trace, type, apiIndex = null, revealPin = false) {
  if (!trace) return 'No exchange selected.';
  const call = apiIndex == null ? null : trace.result.backendExchanges?.[apiIndex];
  if (call) return JSON.stringify(type === 'request' ? {
    stage: call.stage, method: call.method, url: call.url, headers: call.requestHeaders, body: call.requestBody
  } : {stage: call.stage, httpStatus: call.httpStatus, durationMs: call.durationMs,
    outcome: call.outcome, body: call.responseBody}, null, 2);
  let text = type === 'request' ? trace.result.requestXml : trace.result.responseXml;
  if (type === 'request' && trace.sensitive && !revealPin)
    text = (text || '').replace(/(<value>)[\s\S]*?(<\/value>)/, '$1[PIN hidden]$2');
  return text || (type === 'response' ? 'No response body received.' : 'Request was not sent.');
}
