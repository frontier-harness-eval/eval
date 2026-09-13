#!/usr/bin/env node
// Drives a headless Alma instance for one FrontierHarness trial.
//
// Alma is a server application, not a CLI, so it cannot be installed inside the
// task container the way the published harnesses are. Instead Alma runs on the
// Runta runtime host (the same box Harbor/Pier run on) and reaches the task
// container through the ssh → docker-exec shim (eval/ssh-docker-shim.sh), i.e.
// the container is registered as an Alma "remote host". Everything Alma does to
// the task — reading files, editing, running commands — happens inside the
// container through `docker exec`, exactly as it would over ssh.
//
// Subcommands (all speak to Alma over its REST/WS API on 127.0.0.1):
//   ensure-server  start Alma (+ the usage-logging proxy) if not already up
//   configure      create/refresh the Kimi K3 provider and the eval settings
//   run            register the container, send the instruction, wait for the
//                  turn to finish, export tokens/thread/traces to --out
//   stop-server    stop a server started by ensure-server
//
// The Python adapters (alma_harbor_agent.py / alma_pier_agent.py) call this.
import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const execFileP = promisify(execFile);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const cmd = argv[0];
const args = argv.slice(1);
const arg = (name, def) => {
    const i = args.indexOf(`--${name}`);
    return i >= 0 && i + 1 < args.length ? args[i + 1] : def;
};
const flag = name => args.includes(`--${name}`);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.error(new Date().toISOString().slice(11, 19), '[alma-drive]', ...a);

const PORT = parseInt(arg('port', process.env.ALMA_FH_PORT || '23100'), 10);
const BASE = `http://127.0.0.1:${PORT}`;
const PROXY_PORT = parseInt(arg('proxy-port', process.env.ALMA_FH_PROXY_PORT || '8899'), 10);
const HARNESS_DIR = path.resolve(arg('harness-dir', process.env.ALMA_FH_HARNESS_DIR || path.resolve(HERE, '..', '..')));
const DATA_DIR = path.resolve(arg('data-dir', process.env.ALMA_FH_DATA_DIR || '/work/alma-data'));
const LOG_DIR = path.resolve(arg('log-dir', process.env.ALMA_FH_LOG_DIR || '/work/alma/logs'));
const CA_FILE = arg('ca', process.env.ALMA_FH_CA || '/usr/local/share/ca-certificates/runta-egress.crt');
const UPSTREAM_HOST = arg('upstream', process.env.ALMA_FH_UPSTREAM || 'api.fireworks.ai');

const sh = async (bin, a, opts = {}) => {
    try {
        const { stdout, stderr } = await execFileP(bin, a, { maxBuffer: 64 * 1024 * 1024, timeout: 180_000, ...opts });
        return { code: 0, stdout, stderr };
    } catch (e) {
        return { code: e.code ?? 1, stdout: e.stdout ?? '', stderr: e.stderr ?? String(e) };
    }
};
const api = async (method, p, body) => {
    const res = await fetch(`${BASE}${p}`, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await res.text();
    let json;
    try {
        json = JSON.parse(text);
    } catch {
        json = text;
    }
    if (!res.ok) throw new Error(`${method} ${p} → ${res.status}: ${text.slice(0, 300)}`);
    return json;
};
const healthy = async () => {
    try {
        const res = await fetch(`${BASE}/api/health`, { signal: AbortSignal.timeout(3000) });
        return res.ok;
    } catch {
        return false;
    }
};
const proxyUp = async () => {
    try {
        const res = await fetch(`http://127.0.0.1:${PROXY_PORT}/__alma_fh_proxy_health`, { signal: AbortSignal.timeout(2000) });
        return res.status === 200;
    } catch {
        return false;
    }
};

// ── ensure-server ────────────────────────────────────────────────────────────
function serverEnv() {
    const env = {
        ...process.env,
        ALMA_HEADLESS: '1',
        ALMA_PORT: String(PORT),
        ALMA_DATA_DIR: DATA_DIR,
        ALMA_APP_PATH: HARNESS_DIR,
        ALMA_SSH_BIN: path.join(HARNESS_DIR, 'eval', 'ssh-docker-shim.sh'),
        // Empty prefix: every ssh target Alma sees on this host is a task container.
        BENCH_PREFIX: '',
        ALMA_TOOL_APPROVAL: 'allow',
        ALMA_START_HIDDEN: '1',
        ALMA_NO_OPENAI_CACHE_CONTROL: '1',
        HOME: process.env.HOME || os.homedir(),
    };
    if (fs.existsSync(CA_FILE)) env.NODE_EXTRA_CA_CERTS = CA_FILE;
    return env;
}

// Alma runs on the runtime host rather than inside the task container (README
// deviation 1), so nothing holds it to the cpus/memory_mb the task declares for
// its container the way an in-container agent is held. When the runner exports
// the declared numbers, put the server in a transient systemd scope with the
// same limits. Off unless both variables are set.
const CAP_SCOPE = 'alma-fh-server.scope';
function capPrefix() {
    const cpus = process.env.ALMA_FH_CAP_CPUS;
    const memMb = process.env.ALMA_FH_CAP_MEMORY_MB;
    if (!cpus || !memMb) return null;
    return [
        'systemd-run',
        '--scope',
        '--quiet',
        '--collect',
        `--unit=${CAP_SCOPE}`,
        '-p',
        `CPUQuota=${Math.round(parseFloat(cpus) * 100)}%`,
        '-p',
        `MemoryMax=${parseInt(memMb, 10)}M`,
        '-p',
        'MemorySwapMax=0',
        '--',
    ];
}

function spawnDetached(name, script, extraArgs, env, cap = false) {
    fs.mkdirSync(LOG_DIR, { recursive: true });
    const logPath = path.join(LOG_DIR, `${name}.log`);
    const fd = fs.openSync(logPath, 'a');
    const prefix = cap ? capPrefix() : null;
    const [exe, argv] = prefix
        ? [prefix[0], [...prefix.slice(1), process.execPath, script, ...extraArgs]]
        : [process.execPath, [script, ...extraArgs]];
    const child = spawn(exe, argv, { detached: true, stdio: ['ignore', fd, fd], env, cwd: HARNESS_DIR });
    fs.writeFileSync(path.join(LOG_DIR, `${name}.pid`), String(child.pid));
    if (prefix) {
        fs.writeFileSync(path.join(LOG_DIR, `${name}.scope`), CAP_SCOPE);
        log(`capped ${name}: ${prefix[prefix.indexOf('-p') + 1]} MemoryMax=${process.env.ALMA_FH_CAP_MEMORY_MB}M`);
    } else {
        fs.rmSync(path.join(LOG_DIR, `${name}.scope`), { force: true });
    }
    child.unref();
    log(`spawned ${name} pid=${child.pid} log=${logPath}`);
    return child.pid;
}

async function ensureServer() {
    if (!(await proxyUp())) {
        const env = { ...process.env };
        if (fs.existsSync(CA_FILE)) env.NODE_EXTRA_CA_CERTS = CA_FILE;
        fs.mkdirSync(LOG_DIR, { recursive: true });
        spawnDetached('fw-proxy', path.join(HERE, 'fw-proxy.mjs'), [String(PROXY_PORT), path.join(LOG_DIR, 'fw-usage.jsonl'), UPSTREAM_HOST], env);
        for (let i = 0; i < 30 && !(await proxyUp()); i++) await sleep(500);
        if (!(await proxyUp())) throw new Error('usage proxy did not come up');
    }
    if (await healthy()) {
        log(`alma already healthy on :${PORT}`);
        return;
    }
    const serverScript = path.join(HARNESS_DIR, 'bin', 'server.mjs');
    if (!fs.existsSync(serverScript)) throw new Error(`missing ${serverScript}; run install-alma.sh first`);
    spawnDetached('alma-server', serverScript, [], serverEnv(), true);
    const deadline = Date.now() + 180_000;
    while (Date.now() < deadline) {
        if (await healthy()) {
            log(`alma healthy on :${PORT}`);
            return;
        }
        await sleep(1000);
    }
    throw new Error(`alma did not become healthy on :${PORT} within 180s; see ${path.join(LOG_DIR, 'alma-server.log')}`);
}

async function stopServer() {
    for (const name of ['alma-server', 'fw-proxy']) {
        const pidFile = path.join(LOG_DIR, `${name}.pid`);
        if (!fs.existsSync(pidFile)) continue;
        const pid = parseInt(fs.readFileSync(pidFile, 'utf8'), 10);
        const scopeFile = path.join(LOG_DIR, `${name}.scope`);
        if (fs.existsSync(scopeFile)) {
            // The recorded pid is systemd-run's; killing it leaves the scope's
            // process behind. Stop the scope instead.
            const unit = fs.readFileSync(scopeFile, 'utf8').trim();
            try {
                await execFileP('systemctl', ['stop', unit]);
                log(`stopped ${name} scope ${unit}`);
            } catch (e) {
                log(`systemctl stop ${unit} failed: ${e?.message || e}`);
            }
            fs.rmSync(scopeFile, { force: true });
        }
        try {
            process.kill(pid, 'SIGTERM');
            log(`sent SIGTERM to ${name} pid=${pid}`);
        } catch {}
        fs.rmSync(pidFile, { force: true });
    }
    for (let i = 0; i < 20 && (await healthy()); i++) await sleep(500);
}

// ── configure ────────────────────────────────────────────────────────────────
async function configure() {
    const providerId = arg('provider-id', 'fireworks');
    const modelId = arg('model-id', 'accounts/fireworks/models/kimi-k3');
    const baseURL = arg('base-url', `http://127.0.0.1:${PROXY_PORT}/inference/v1`);
    const apiKey = arg('api-key', 'runta-secret-stub');
    // Kimi K3's context window as Fireworks reports it (`context_length` in
    // GET /inference/v1/models, read 2026-09-06: 1048576). Without a declared
    // window Alma assumes 128k for a manual model and starts compacting at
    // 80% of that, so trials lost history to summaries long before the model
    // was anywhere near its limit.
    const contextWindow = parseInt(arg('context-window', process.env.ALMA_FH_CONTEXT_WINDOW || '1048576'), 10);
    const providers = await api('GET', '/api/providers');
    const body = { id: providerId, name: providerId, type: 'custom', apiKey, baseURL, enabled: true, models: [modelId] };
    const existing = Array.isArray(providers) ? providers.find(p => p.id === providerId) : null;
    if (existing) {
        await api('PUT', `/api/providers/${providerId}`, body);
        log(`updated provider ${providerId}`);
    } else {
        await api('POST', '/api/providers', body);
        log(`created provider ${providerId}`);
    }
    // The model list of a custom provider is whatever the operator declares.
    // The eval runtime cannot reach models.dev (egress allowlist), so Alma's
    // auto-detected capabilities for the model are empty; declare function
    // calling explicitly the same way a user would in Settings, otherwise the
    // server falls back to the text-based tool middleware. The context window
    // is declared for the same reason (see contextWindow above).
    //
    // Deliberately NOT set: settings.toolModel. Alma's BashAnalyzer sends every
    // command it cannot classify locally to the tool model, so configuring one
    // would spend an extra model call per Bash invocation (922 of them in the
    // first full run). The eval selects the tool set explicitly instead (see
    // run()), which needs no tool model.
    await api('PUT', `/api/providers/${providerId}/models`, {
        models: [modelId],
        availableModels: [{ id: modelId, name: modelId, isManual: true, capabilityOverrides: { functionCalling: true, contextWindow } }],
    }).catch(e => log(`models update skipped: ${e.message}`));

    const settings = await api('GET', '/api/settings');
    const set = (obj, keyPath, value) => {
        const keys = keyPath.split('.');
        let cur = obj;
        for (const k of keys.slice(0, -1)) cur = cur[k] ?? (cur[k] = {});
        cur[keys[keys.length - 1]] = value;
    };
    // Eval profile — the same one the earlier Runta rounds used, so results stay
    // comparable: tool calls auto-approved (no human in the loop), programmatic
    // tool calling off. Everything else stays at Alma's shipped defaults; the
    // product is measured as shipped, side features included. Analytics is the
    // one exception (the egress allowlist blocks it anyway; off avoids noise).
    // ALMA_FH_LEAN=1 additionally turns off the features that spend model calls
    // outside the task turn (memory, skill extraction, suggestions).
    set(settings, 'chat.defaultModel', `${providerId}:${modelId}`);
    set(settings, 'security.autoApproveToolRequests', true);
    set(settings, 'advanced.programmaticToolCalling', false);
    set(settings, 'general.analyticsEnabled', false);
    if (process.env.ALMA_FH_LEAN === '1') {
        set(settings, 'memory.enabled', false);
        set(settings, 'skillExtraction.enabled', false);
        set(settings, 'chat.autoSuggestions.enabled', false);
    }
    await api('PUT', '/api/settings', settings);
    log('settings applied');
    const check = await api('GET', '/api/providers');
    const p = Array.isArray(check) ? check.find(x => x.id === providerId) : null;
    if (!p) throw new Error('provider not visible after configure');
    console.log(JSON.stringify({ providerId, modelId, baseURL, contextWindow, type: p.type, models: p.models }, null, 1));
}

// ── run ──────────────────────────────────────────────────────────────────────
async function waitForContainer(container) {
    const deadline = Date.now() + 120_000;
    while (Date.now() < deadline) {
        const r = await sh('docker', ['inspect', '-f', '{{.State.Running}}', container]);
        if (r.code === 0 && r.stdout.trim() === 'true') return;
        await sleep(2000);
    }
    throw new Error(`container ${container} is not running`);
}

async function injectNode(container, nodeBin) {
    // Alma's remote-workspace daemon runs on node inside the workspace host.
    // Task images rarely ship one, so drop in a static binary (same as the
    // earlier Runta rounds). Never overwrite a node the image already has.
    const have = await sh('docker', ['exec', container, 'sh', '-c', 'command -v node >/dev/null 2>&1 && node -e "process.exit(parseInt(process.versions.node)>=18?0:1)"']);
    if (have.code === 0) return 'image';
    if (!nodeBin || !fs.existsSync(nodeBin)) throw new Error(`no node in ${container} and no --node-bin to inject`);
    const cp = await sh('docker', ['cp', nodeBin, `${container}:/usr/local/bin/node`]);
    if (cp.code !== 0) throw new Error(`docker cp node failed: ${cp.stderr.slice(0, 300)}`);
    await sh('docker', ['exec', container, 'chmod', '+x', '/usr/local/bin/node']);
    return 'injected';
}

async function registerWorkspace(container, workdir, label, model) {
    let host = await api('POST', '/api/remote-hosts', { name: label, sshTarget: container, source: 'manual' }).catch(e => ({ __err: String(e) }));
    if (host.__err) {
        const hosts = await api('GET', '/api/remote-hosts').catch(() => []);
        const existing = Array.isArray(hosts) ? hosts.find(h => h.sshTarget === container) : null;
        if (!existing) throw new Error(host.__err);
        host = { host: existing };
    }
    const hostId = host.host?.id ?? host.id;
    let ws = await api('POST', '/api/workspaces', { path: workdir, name: label, remoteHostId: hostId }).catch(e => ({ __err: String(e) }));
    if (ws.__err) {
        const all = await api('GET', '/api/workspaces').catch(() => []);
        const existing = Array.isArray(all) ? all.find(w => w.remoteHostId === hostId && w.path === workdir) : null;
        if (!existing) throw new Error(ws.__err);
        ws = { workspace: existing };
    }
    const wsId = ws.workspace?.id ?? ws.id;
    const thread = await api('POST', '/api/threads', { title: label, model });
    await api('PUT', `/api/threads/${thread.id}`, { workspaceId: wsId });
    return { hostId, wsId, threadId: thread.id };
}

function wsSend(type, data) {
    return new Promise((resolve, reject) => {
        const sock = new WebSocket(`ws://127.0.0.1:${PORT}/ws/threads`);
        const timer = setTimeout(() => {
            try {
                sock.close();
            } catch {}
            reject(new Error('ws send timed out'));
        }, 15_000);
        sock.addEventListener('open', () => {
            sock.send(JSON.stringify({ type, data }));
            setTimeout(() => {
                clearTimeout(timer);
                sock.close();
                resolve();
            }, 1200);
        });
        sock.addEventListener('error', e => {
            clearTimeout(timer);
            reject(new Error('ws error: ' + (e.message || 'unknown')));
        });
    });
}

function describeThreadError(t) {
    const msgs = t?.messages ?? t?.thread?.messages ?? [];
    for (const m of [...msgs].reverse()) {
        for (const p of m?.parts ?? []) {
            const txt = p?.errorText || p?.text || '';
            if (/error|unsupported|unauthorized|forbidden|not found|invalid/i.test(txt)) return txt.slice(0, 300);
        }
    }
    return null;
}

let stopRequested = false;
async function waitForTurn(threadId, timeoutSec, opts = {}) {
    const deadline = Date.now() + timeoutSec * 1000;
    const startBy = Date.now() + Math.min(120_000, timeoutSec * 1000);
    const steerAt = opts.steerLeadSec > 0 && opts.onSteer ? deadline - opts.steerLeadSec * 1000 : Infinity;
    let sawGenerating = false;
    let steered = false;
    while (Date.now() < deadline && !stopRequested) {
        await sleep(5000);
        let t;
        try {
            t = await api('GET', `/api/threads/${threadId}`);
        } catch {
            continue;
        }
        if (t.isGenerating) sawGenerating = true;
        else if (sawGenerating) return { finished: true };
        else if (Date.now() > startBy) {
            const why = describeThreadError(t) || 'no error recorded on the thread — check alma-server.log and the provider config';
            throw new Error(`generation never started: ${why}`);
        }
        // Steer only into a turn that is live right now; if it has already
        // ended the loop returns above and no new turn is ever started.
        if (!steered && t.isGenerating && Date.now() >= steerAt) {
            steered = true;
            try {
                await opts.onSteer(Math.round((deadline - Date.now()) / 1000));
            } catch (e) {
                log(`steer failed: ${e?.message || e}`);
            }
        }
    }
    return { finished: false, timedOut: !stopRequested };
}

async function collectUsage(threadId) {
    const thread = await api('GET', `/api/threads/${threadId}`).catch(() => null);
    const ops = await api('GET', `/api/threads/${threadId}/traces?limit=500`).then(r => r.traces ?? []).catch(() => []);
    const traces = [];
    const tok = { input: 0, cached: 0, output: 0, reasoning: 0, cacheWrite: 0 };
    let steps = 0;
    let llmCalls = 0;
    for (const op of ops) {
        const full = await api('GET', `/api/messages/${op.messageId}/trace`).catch(() => null);
        if (!full) continue;
        traces.push(full);
        for (const s of full.steps ?? []) {
            steps += 1;
            llmCalls += 1;
            tok.input += s.inputTokens ?? 0;
            tok.cached += s.cachedInputTokens ?? 0;
            tok.output += s.outputTokens ?? 0;
            tok.reasoning += s.reasoningTokens ?? 0;
            tok.cacheWrite += s.cacheWriteInputTokens ?? 0;
        }
    }
    let source = 'traces';
    if (steps === 0 && thread) {
        // Fallback: the per-message usage totals Alma stores in message metadata.
        source = 'messages';
        for (const m of thread.messages ?? []) {
            const u = m?.metadata?.usage;
            if (!u) continue;
            tok.input += u.inputTokens ?? 0;
            tok.cached += u.cachedInputTokens ?? 0;
            tok.output += u.outputTokens ?? 0;
            tok.reasoning += u.reasoningTokens ?? 0;
        }
    }
    // Alma records how each turn actually ended (op.status / op.errorMessage).
    // waitForTurn cannot see that -- it only watches isGenerating flip to false,
    // which happens identically whether the agent finished its work or the
    // provider killed the stream. Reporting "finished" for the second case is
    // how a trial whose model calls all failed got scored as an ordinary agent
    // failure. Carry the recorded verdict out so the trial record can't lie.
    const errored = traces.filter(t => t?.op?.status === 'error');
    const turnStatus = errored.length ? 'error' : traces.length ? (traces[traces.length - 1]?.op?.status ?? null) : null;
    const turnError = errored.length ? String(errored[errored.length - 1].op.errorMessage ?? '').split('\n')[0].slice(0, 300) : null;

    return { thread, traces, tokens: tok, steps, llmCalls, source, turnStatus, turnError };
}

async function readProxyUsage(sinceMs, agentDir) {
    // Independent ground truth: the logging proxy records every upstream
    // response's usage block. Trials run one at a time on a fresh runtime, so
    // everything after `sinceMs` belongs to this trial.
    //
    // The slice is also written to the trial's agent directory, because that is
    // where the official scorer looks for per-call usage: calculate-cost.py
    // calls usage_details.extract_usage_details(<leaf result.json>/../agent,
    // harness), and every published harness drops its own per-call log there
    // (pi.txt, opencode.txt, hermes-calls.jsonl, ...). Without it a trial has no
    // turn count and no first-call cache split, so the first-cold repricing the
    // report ranks on cannot be computed at all.
    const p = path.join(LOG_DIR, 'fw-usage.jsonl');
    const tot = { requests: 0, prompt: 0, cached: 0, completion: 0 };
    if (!fs.existsSync(p)) return tot;
    const mine = [];
    for (const line of fs.readFileSync(p, 'utf8').split('\n')) {
        if (!line.trim()) continue;
        try {
            const r = JSON.parse(line);
            if (r.t < sinceMs) continue;
            mine.push(line.trim());
            tot.requests += 1;
            tot.prompt += r.prompt ?? 0;
            tot.cached += r.cached ?? 0;
            tot.completion += r.completion ?? 0;
        } catch {}
    }
    if (agentDir) {
        try {
            fs.writeFileSync(path.join(agentDir, 'fw-usage.jsonl'), mine.length ? mine.join('\n') + '\n' : '');
        } catch {}
    }
    return tot;
}

async function run() {
    const model = arg('model');
    const container = arg('container');
    const workdir = arg('workdir', '/app');
    const instructionFile = arg('instruction-file');
    const out = arg('out');
    const timeoutSec = parseInt(arg('timeout-sec', '5400'), 10);
    const nodeBin = arg('node-bin', process.env.ALMA_FH_NODE_BIN || '');
    const label = arg('label', `fh:${container}`);
    // Tool selection. Alma's composer sends either `['__auto__']` (the model
    // picks tools per message through the configured tool model) or the
    // explicit list the user ticked. The first full run sent neither, which the
    // server treats as an empty selection: only the skill-required Bash/Skill
    // pair (plus the always-on ToolSearch/AskUserQuestion/widgets) reached the
    // model, and ToolSearch itself was dead without a tool model — 922 Bash
    // calls, zero Read/Write/Edit/Grep/Glob, in 30 trials. Auto mode would
    // need a tool model (see configure()); the explicit list is the other
    // first-class path and is what a user doing coding work ticks.
    const toolKeys = arg('tools', process.env.ALMA_FH_TOOLS || 'Bash,BashOutput,KillShell,Read,Write,Edit,Glob,Grep')
        .split(',')
        .map(s => s.trim())
        .filter(Boolean);
    // Wrap-up steer: `steerLeadSec` before the agent deadline, fold one user
    // message into the running turn telling the model how much time is left.
    // Two trials of the first run were killed by the official 5400 s wrapper
    // mid-work (one ~10 min from a plausible pass) and never reached the
    // verifier. 0 disables.
    const steerLeadSec = parseInt(arg('steer-lead-sec', process.env.ALMA_FH_STEER_LEAD_SEC || '600'), 10);
    if (!model || !container || !instructionFile || !out) throw new Error('run needs --model --container --instruction-file --out');
    const result = {
        container,
        model,
        workdir,
        label,
        startedAt: new Date().toISOString(),
        finishedAt: null,
        finished: false,
        turnStatus: null,
        turnError: null,
        timedOut: false,
        error: null,
        threadId: null,
        tools: toolKeys,
        steeredAt: null,
        tokens: null,
        steps: null,
        proxyUsage: null,
    };
    const writeOut = () => fs.writeFileSync(out, JSON.stringify(result, null, 1));
    writeOut();

    // Instance-identity guard: refuse to drive anything but the eval instance.
    const provs = await api('GET', '/api/providers');
    const providerId = model.split(':')[0];
    if (!Array.isArray(provs) || !provs.some(p => p.id === providerId)) {
        throw new Error(`REFUSING: :${PORT} has no provider '${providerId}' — not the eval instance`);
    }

    await waitForContainer(container);
    result.nodeSource = await injectNode(container, nodeBin);
    await sh('docker', ['exec', container, 'sh', '-c', `mkdir -p '${workdir}'`]);
    const ids = await registerWorkspace(container, workdir, label, model);
    result.threadId = ids.threadId;
    const instruction = fs.readFileSync(instructionFile, 'utf8');
    const t0 = Date.now();
    result.agentStartedAt = new Date(t0).toISOString();
    writeOut();

    const onStop = async () => {
        stopRequested = true;
    };
    process.on('SIGTERM', onStop);
    process.on('SIGINT', onStop);

    try {
        await wsSend('generate_response', { threadId: ids.threadId, model, tools: toolKeys, userMessage: { role: 'user', parts: [{ type: 'text', text: instruction }] }, source: 'frontierharness-eval' });
        const turn = await waitForTurn(ids.threadId, timeoutSec, {
            steerLeadSec,
            onSteer: async remainingSec => {
                const minutes = Math.max(1, Math.round(remainingSec / 60));
                const text =
                    `<system-reminder>Time check: about ${minutes} minutes remain before this session is terminated and the work is evaluated as-is. ` +
                    'Do not start new investigations. Make sure the required changes are in place, run the relevant tests once, ' +
                    'clean up any temporary files you created, and finish (commit if the task asked for it). ' +
                    'No reply to this reminder is needed.</system-reminder>';
                await wsSend('steer_generation', { threadId: ids.threadId, model, userMessage: { role: 'user', parts: [{ type: 'text', text }] }, source: 'frontierharness-eval' });
                result.steeredAt = new Date().toISOString();
                writeOut();
                log(`steer sent with ~${minutes} min left`);
            },
        });
        result.finished = turn.finished;
        result.timedOut = Boolean(turn.timedOut);
        result.stopped = stopRequested;
        if (!turn.finished) {
            await wsSend('stop_generation', { threadId: ids.threadId }).catch(() => {});
            await sleep(3000);
        }
    } catch (e) {
        result.error = String(e?.message || e);
        log(`run error: ${result.error}`);
    }
    result.agentSeconds = Math.round((Date.now() - t0) / 1000);
    result.finishedAt = new Date().toISOString();

    try {
        const usage = await collectUsage(ids.threadId);
        result.tokens = usage.tokens;
        result.steps = usage.steps;
        result.llmCalls = usage.llmCalls;
        result.usageSource = usage.source;
        result.turnStatus = usage.turnStatus;
        result.turnError = usage.turnError;
        // "The agent stopped generating" is not "the agent finished". A turn the
        // provider aborted must not be reported as a completed attempt.
        if (usage.turnStatus === 'error') {
            result.finished = false;
            result.error = result.error || `turn ended in error: ${usage.turnError || 'unspecified'}`;
        }
        const evidenceDir = path.join(path.dirname(out), 'alma-thread');
        fs.mkdirSync(evidenceDir, { recursive: true });
        fs.writeFileSync(path.join(evidenceDir, 'thread.json'), JSON.stringify(usage.thread, null, 1));
        fs.writeFileSync(path.join(evidenceDir, 'traces.json'), JSON.stringify(usage.traces, null, 1));
    } catch (e) {
        result.usageError = String(e?.message || e);
    }
    result.proxyUsage = await readProxyUsage(t0, path.dirname(out));
    writeOut();

    // Tear down the remote-host registration so the in-container daemon exits
    // before the verifier runs. The thread stays in Alma's DB as evidence.
    for (const [kind, id] of [['workspaces', ids.wsId], ['remote-hosts', ids.hostId]]) {
        if (id) await api('DELETE', `/api/${kind}/${id}`).catch(() => {});
    }
    log(`done: finished=${result.finished} turnStatus=${result.turnStatus ?? 'n/a'}${result.turnError ? ` turnError=${result.turnError}` : ''} timedOut=${result.timedOut} steps=${result.steps} tokens=${JSON.stringify(result.tokens)} proxy=${JSON.stringify(result.proxyUsage)}`);
    if (result.error) process.exitCode = 3;
}

const main = { 'ensure-server': ensureServer, configure, run, 'stop-server': stopServer }[cmd];
if (!main) {
    console.error('usage: alma-drive.mjs <ensure-server|configure|run|stop-server> [--flags]');
    process.exit(2);
}
main().catch(e => {
    log(`fatal: ${e?.stack || e}`);
    process.exit(1);
});
