# Public execution evidence

The evidence covers all 30 formal tasks, including all seven failures. There was no additional model run for this publication.

Download the [trace bundle, manifest, and SHA256SUMS](https://github.com/Astro-Han/eval/releases/tag/maka-kimi-k3-20260912-evidence). The release is hosted on the submission fork to avoid adding large binary archives to the upstream Git history.

## Contents

Each task has a directory named `NN-suite-task` containing:

- `runtime-events.jsonl`: every persisted Runtime Host event exported from that task's SQLite database, including model text/reasoning where recorded, tool calls, and tool responses.
- `evidence/budget-state/`: recorded outbound request bodies, provider response bodies/streams, request status, and timing/accounting records. System prompts and tool schemas can be inspected in the request JSON. Request bodies do not constitute captured HTTP headers.
- `evidence/trial/`: native results, verifier output, execution logs, and retained task artifacts. DeepSWE changes are in `jobs/*/artifacts/model.patch`.

`MANIFEST.json` lists every exported file with its byte size and SHA256, the original local archive hash for each task, and omissions. `SHA256SUMS` verifies the downloadable compressed bundle. The public bundle is a new export; its hash is intentionally different from the original per-task archive hashes in `observed-results.json`.

```sh
shasum -a 256 -c SHA256SUMS
tar -xzf maka-kimi-k3-20260912-traces.tar.gz
```

To read a task, start with its verifier output and then open `runtime-events.jsonl`; events retain their original sequence and payload. Request/response files provide the provider-facing record. Failed tasks are 07 (DNA), 12 (eigenvalue), 18 (polyglot), 22 (Anko), 24 (Expr), 28 (Meriyah), and 30 (SCC). `observed-results.json` remains the task-level result index.

## Privacy and fidelity

No textual content was redacted or rewritten in this export. A scan and contextual review found no live provider credentials in the exported text. Credential-shaped strings in the repository-sanitization task are benchmark fixtures and are preserved, as are public source-author identities and test data. Provider-key, Bearer-token, private-key, signed-download-URL, and local macOS home-path patterns were checked; generic secret/password assignments were reviewed in their task context. This is a scoped publication check, not a claim that pattern scanning proves the absence of every possible secret.

The 30 SQLite containers are omitted because an event export is readable without database tooling and does not carry unused database pages. All persisted `runtime_events` are included; other SQLite tables are not exported. Original databases and original evidence archives remain retained locally. Infrastructure smoke/invalid attempts, account billing files, and control-plane credentials are outside this formal-task bundle.

Recorded evidence can have gaps from the original run: in particular, the final interrupted request in task 12 has no final usage record, and Anko's retained verifier output lacks the precise new-suite compiler diagnostic. Publication does not reconstruct missing data or alter the original result.
