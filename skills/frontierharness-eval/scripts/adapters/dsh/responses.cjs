'use strict';
const fs = require('node:fs');
const keyFile = '/tmp/.fh-dsh-key';
const key = fs.readFileSync(keyFile, 'utf8').trim();
fs.unlinkSync(keyFile);
const endpoint = process.env.FH_DSH_RESPONSES_URL;
const maxKeywords = Number(process.env.FH_DSH_WEB_SEARCH_MAX_KEYWORDS);
const fetch = globalThis.fetch.bind(globalThis);

globalThis.fetch = async function (input, init) {
  const url = typeof input === 'string' ? input : input.url ?? input.href;
  if (url !== endpoint) return fetch(input, init);
  const request = new Request(input, init);
  const headers = new Headers(request.headers);
  headers.set('authorization', 'Bearer ' + key);
  const body = await request.json();
  if (maxKeywords) {
    const tools = (body.tools ?? []).filter(tool => tool.type !== 'web_search' && tool.name !== 'web_search');
    body.tools = [...tools, { type: 'web_search', max_keyword: maxKeywords }];
  }
  headers.delete('content-length');
  const response = await fetch(url, {
    method: request.method, headers, body: JSON.stringify(body), signal: request.signal, redirect: 'error',
  });
  fs.appendFileSync('/logs/agent/dsh-requests.jsonl', JSON.stringify({
    status: response.status, model: body.model, tool_types: (body.tools ?? []).map(tool => tool.type),
    max_keyword: maxKeywords || null, request_id: response.headers.get('x-request-id'),
  }) + '\n');
  return response;
};
