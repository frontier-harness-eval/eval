#!/usr/bin/env node
// Logging proxy: Alma → here → the Kimi K3 provider. Records the usage block of
// every chat completion (prompt_tokens, completion_tokens,
// prompt_tokens_details.cached_tokens) from both streaming and non-streaming
// responses, giving an accounting of tokens that is independent of Alma's own
// ledger. Runta's egress proxy still terminates TLS and injects the real key,
// so the Authorization header forwarded here is only ever the secret stub.
//
//   fw-proxy.mjs [port] [log.jsonl] [upstreamHost]
import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';

const PORT = Number(process.argv[2] || 8899);
const LOG = process.argv[3] || 'fw-usage.jsonl';
const UPSTREAM = process.argv[4] || 'api.fireworks.ai';

const record = u => {
    try {
        fs.appendFileSync(LOG, JSON.stringify({ t: Date.now(), ...u }) + '\n');
    } catch {}
};
const extractUsage = text => {
    // Last "usage" object wins (final SSE chunk or plain JSON body).
    let found = null;
    const re = /"usage"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})/g;
    let m;
    while ((m = re.exec(text))) {
        try {
            found = JSON.parse(m[1]);
        } catch {}
    }
    return found;
};

http.createServer((req, res) => {
    if (req.url === '/__alma_fh_proxy_health') {
        res.writeHead(200, { 'content-type': 'text/plain' });
        res.end('ok');
        return;
    }
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
        const body = Buffer.concat(chunks);
        const headers = { ...req.headers, host: UPSTREAM };
        delete headers['content-length'];
        if (body.length) headers['content-length'] = String(body.length);
        const up = https.request({ hostname: UPSTREAM, path: req.url, method: req.method, headers }, ur => {
            res.writeHead(ur.statusCode || 200, ur.headers);
            const out = [];
            ur.on('data', c => {
                out.push(c);
                res.write(c);
            });
            ur.on('end', () => {
                res.end();
                if (/chat\/completions/.test(req.url || '')) {
                    const u = extractUsage(Buffer.concat(out).toString('utf8'));
                    record({
                        status: ur.statusCode,
                        prompt: u?.prompt_tokens ?? null,
                        completion: u?.completion_tokens ?? null,
                        cached: u?.prompt_tokens_details?.cached_tokens ?? 0,
                    });
                }
            });
        });
        up.on('error', e => {
            record({ status: 502, error: String(e) });
            try {
                res.writeHead(502);
                res.end(JSON.stringify({ error: String(e) }));
            } catch {}
        });
        if (body.length) up.write(body);
        up.end();
    });
}).listen(PORT, '127.0.0.1', () => console.log(`fw-proxy on :${PORT} → ${UPSTREAM}, logging ${LOG}`));
