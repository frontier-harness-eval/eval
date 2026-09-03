#!/usr/bin/env node
// npx entry point for the frontierharness-eval skill.
//
// The skill and its scripts resolve benchmark.json, results/eval-data.json and tasks/
// relative to the working directory, so "using the skill" means having those files on
// disk and pointing an agent at SKILL.md. This CLI does both without a clone: it
// materializes a workspace out of the published package, links the skill into the
// directories coding agents read skills from, and forwards the skill's own scripts so
// the commands in SKILL.md work unchanged from anywhere.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { cp, lstat, mkdir, readFile, rm, symlink } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = resolve(fileURLToPath(import.meta.url), "../..");
const SKILL_DIR = join("skills", "frontierharness-eval");
const SCRIPTS_DIR = join(SKILL_DIR, "scripts");
const DEFAULT_WORKSPACE = "frontierharness-eval";

// What a workspace holds, and what proves a directory already is one (a clone of the
// repository qualifies, which is why running this inside one copies nothing).
const WORKSPACE_ENTRIES = ["benchmark.json", "metadata", "results", "skills", "tasks"];
const WORKSPACE_MARKERS = ["benchmark.json", join("results", "eval-data.json"), "tasks"];

// Where each agent reads skills from, and the home directory that shows it is in use.
const AGENTS = {
  cursor: { skills: join(".cursor", "skills"), markers: [".cursor"] },
  claude: { skills: join(".claude", "skills"), markers: [".claude"] },
  codex: { skills: join(".agents", "skills"), markers: [".agents", ".codex"] },
};

// SKILL.md step -> script, so `npx @frontierharness/eval run` is the documented
// $FH/run-trials.sh with the workspace as its working directory.
const SCRIPTS = {
  provision: "provision-golden-checkpoint.sh",
  run: "run-trials.sh",
  normalize: "normalize-results.mjs",
  chart: "generate-chart.mjs",
  report: "build-report.mjs",
};

const BOOLEAN_FLAGS = new Set(["global", "force", "copy", "smoke", "help", "version"]);

await main(process.argv.slice(2)).catch(error => die(process.env.DEBUG ? error : `${error.message}`));

async function main(argv) {
  const [first, ...rest] = argv;
  // Bare flags such as `npx @frontierharness/eval --global` still mean install.
  const command = !first || first.startsWith("-") ? "install" : first;
  const args = command === first ? rest : argv;

  if (first === "--version" || first === "-v") return console.log(await packageVersion());
  // --help on a forwarded command belongs to the script, which documents more than this.
  if (!(command in SCRIPTS) && (args.includes("--help") || args.includes("-h"))) return usage();

  switch (command) {
    case "install": return install(args);
    case "doctor": return doctor(args);
    case "prompt": return prompt(args);
    case "where": return where(args);
    case "help": return usage();
    case "provision": case "run": case "normalize": case "chart": case "report":
      return forward(command, args);
    default:
      die(`unknown command "${command}"\n\n${usageText()}`);
  }
}

// 1. Materialize the workspace and put the skill where agents look for it.

async function install(argv) {
  const { flags } = parseFlags(argv);
  const workspace = resolveWorkspace(flags);
  const version = await packageVersion();

  console.log(`FrontierHarness Eval ${version}\n`);

  const placed = await materialize(workspace, flags);
  console.log(`workspace  ${tilde(workspace)}`);
  for (const [state, entries] of Object.entries(placed)) {
    if (entries.length) console.log(`  ${state.padEnd(8)} ${entries.join(", ")}`);
  }

  const base = flags.global ? homedir() : workspace;
  const links = [];
  for (const agent of selectAgents(flags.agent)) {
    const linkPath = join(base, AGENTS[agent].skills, "frontierharness-eval");
    await mkdir(dirname(linkPath), { recursive: true });
    links.push({ agent, linkPath, state: await placeSkill(join(workspace, SKILL_DIR), linkPath, flags) });
  }

  console.log(`\nskill      ${tilde(join(workspace, SKILL_DIR))}`);
  if (!links.length) console.log("  (no agent install requested)");
  for (const { agent, linkPath, state } of links) {
    console.log(`  ${state.padEnd(8)} ${agent.padEnd(6)} ${tilde(linkPath)}`);
  }
  if (links.some(link => link.state === "linked")) {
    console.log("  symlinked to the workspace copy; pass --copy for standalone copies");
  }
  if (links.some(link => link.state === "kept")) {
    console.log("  an existing directory was left alone; pass --force to replace it");
  }

  const cd = relative(process.cwd(), workspace);
  console.log(`
Next:
  ${cd ? `cd ${cd}` : "# already in the workspace"}
  export RUNTA_TOKEN=rt_...        # Runta dashboard -> Settings -> Runta API Keys
  export FIREWORKS_API_KEY=...     # or the key for whichever --provider you use
  npx @frontierharness/eval doctor  # check prerequisites before spending anything

Then either open the workspace in your agent and paste the driving prompt:
  npx @frontierharness/eval prompt --harness my-harness --repo https://github.com/acme/my-harness --commit 9f2c1ab
or run the steps yourself:
  npx @frontierharness/eval provision --help`);
}

async function materialize(workspace, flags) {
  const placed = { added: [], updated: [], kept: [] };
  // Running inside a clone (or the package itself): the files are already in place.
  if (workspace === PKG_ROOT) {
    placed.kept.push(...WORKSPACE_ENTRIES);
    return placed;
  }

  await mkdir(workspace, { recursive: true });
  for (const entry of WORKSPACE_ENTRIES) {
    const target = join(workspace, entry);
    const exists = existsSync(target);
    if (exists && !flags.force) {
      placed.kept.push(entry);
      continue;
    }
    await cp(join(PKG_ROOT, entry), target, { recursive: true, force: true });
    placed[exists ? "updated" : "added"].push(entry);
  }
  return placed;
}

async function placeSkill(skillDir, linkPath, flags) {
  const current = await lstat(linkPath).catch(() => null);
  if (current) {
    // A stale symlink is ours to refresh; a real directory may be someone's edits.
    if (!current.isSymbolicLink() && !flags.force) return "kept";
    await rm(linkPath, { recursive: true, force: true });
  }

  if (!flags.copy) {
    try {
      // Relative, so one copy of the skill serves every agent and survives a move.
      await symlink(relative(dirname(linkPath), skillDir), linkPath, "dir");
      return "linked";
    } catch {
      // Windows without developer mode, or a filesystem with no symlink support.
    }
  }
  await cp(skillDir, linkPath, { recursive: true, force: true });
  return "copied";
}

function selectAgents(value) {
  const known = Object.keys(AGENTS);
  if (value === "none") return [];
  if (value === "all") return known;
  if (value && value !== "auto") {
    const names = value.split(",").map(name => name.trim()).filter(Boolean);
    for (const name of names) {
      if (!AGENTS[name]) die(`unknown --agent "${name}"; expected ${known.join(", ")}, all, auto or none`);
    }
    return names;
  }
  // Auto: whichever agents this machine already uses, all of them on a fresh box.
  const detected = known.filter(name =>
    AGENTS[name].markers.some(marker => existsSync(join(homedir(), marker))));
  return detected.length ? detected : known;
}

// 2. Prerequisites, checked before a run rather than halfway through one.

async function doctor(argv) {
  const { flags } = parseFlags(argv);
  const provider = flags.provider ?? "fireworks";
  const workspace = resolveWorkspace(flags);
  const scriptsDir = existsSync(join(workspace, SCRIPTS_DIR))
    ? join(workspace, SCRIPTS_DIR)
    : join(PKG_ROOT, SCRIPTS_DIR);

  const providers = await providerTable(scriptsDir);
  if (!(provider in providers)) {
    die(`unknown --provider "${provider}"; expected ${Object.keys(providers).join(", ")}`);
  }
  const secret = providers[provider];

  const node = Number(process.versions.node.split(".")[0]);
  const results = [
    { label: "node >= 18", ok: node >= 18, detail: process.version, hint: "install Node 18 or newer" },
    { label: "workspace", ok: isWorkspace(workspace), detail: tilde(workspace), hint: "run: npx @frontierharness/eval" },
    await checkCommand("runta CLI", "runta", ["--version"], "brew install runta-dev/tap/runta"),
    await checkCommand("jq", "jq", ["--version"], "brew install jq"),
    // The same probe require_runta_auth() uses: RUNTA_TOKEN and `runta login` both
    // count, and a token that is set but stale is caught here rather than mid-run.
    await checkCommand("runta API reachable", "runta", ["checkpoint", "ls"],
      "set RUNTA_TOKEN (Runta dashboard -> Settings -> Runta API Keys) or run: runta login",
      process.env.RUNTA_TOKEN ? "authenticated by RUNTA_TOKEN" : "authenticated"),
  ];
  if (secret) {
    results.push(checkEnv(`${secret} (--provider ${provider})`, secret, `export ${secret}=... for ${provider}`));
  } else {
    console.log(`--provider custom: supply --model and --secret-name yourself\n`);
  }

  for (const { label, ok, detail, hint } of results) {
    console.log(`${ok ? "ok     " : "missing"}  ${label.padEnd(30)} ${ok ? detail ?? "" : hint}`);
  }

  const failed = results.filter(result => !result.ok);
  if (failed.length) {
    console.error(`\n${failed.length} prerequisite(s) missing; fix them before provisioning.`);
    process.exit(1);
  }
  console.log("\nAll prerequisites present.");
}

async function checkCommand(label, command, args, hint, summary) {
  const ok = await new Promise(done => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "ignore"] });
    let out = "";
    child.stdout.on("data", chunk => { out += chunk; });
    child.on("error", () => done(null));
    // Output stands in for the detail column unless the caller supplies one, since a
    // listing command says nothing useful there.
    child.on("close", code => done(code === 0 ? summary ?? out.trim().split("\n")[0] ?? "ok" : null));
  });
  return { label, ok: Boolean(ok), detail: ok, hint };
}

function checkEnv(label, name, hint) {
  const value = process.env[name];
  return { label, ok: Boolean(value), detail: value ? `${value.slice(0, 3)}...` : "", hint };
}

// The provider table lives in providers.sh so the scripts and this CLI cannot disagree.
async function providerTable(scriptsDir) {
  const text = await readFile(join(scriptsDir, "providers.sh"), "utf8");
  const list = /^PROVIDER_LIST="([^"]+)"/m.exec(text);
  const table = {};
  for (const provider of (list?.[1] ?? "").split(/\s+/).filter(Boolean)) {
    const section = new RegExp(`^\\s+${provider}\\)([\\s\\S]*?);;`, "m").exec(text);
    table[provider] = /PROVIDER_SECRET="([^"]*)"/.exec(section?.[1] ?? "")?.[1] || null;
  }
  return table;
}

// 3. The copy-paste prompt, with the blanks PROMPT.md asks for already filled in.

async function prompt(argv) {
  const { flags } = parseFlags(argv);
  const workspace = resolveWorkspace(flags);
  const source = existsSync(join(workspace, SKILL_DIR, "PROMPT.md"))
    ? join(workspace, SKILL_DIR, "PROMPT.md")
    : join(PKG_ROOT, SKILL_DIR, "PROMPT.md");
  const text = await readFile(source, "utf8");

  let body = /## The prompt\s+```text\n([\s\S]*?)```/.exec(text)?.[1];
  if (!body) die(`could not find the prompt block in ${source}`);

  if (flags.smoke) {
    const smoke = /## Try it on two tasks first[\s\S]*?```text\n([\s\S]*?)```/.exec(text)?.[1];
    if (!smoke) die(`could not find the two-task block in ${source}`);
    // Swap the full 30-task sweep for the two-task version, keeping everything else.
    body = body.replace(/^5\. [\s\S]*?(?=^6\. )/m, `${smoke.trimEnd()}\n\n`);
  }

  const fills = {
    "<HARNESS_NAME>": flags.harness,
    "<REPO_URL>": flags.repo,
    "<COMMIT_SHA>": flags.commit,
    "<PROVIDER>": flags.provider,
    "<BUILD_STEPS>": flags.build,
  };
  for (const [placeholder, value] of Object.entries(fills)) {
    if (value) body = body.split(placeholder).join(value);
  }

  console.log(body.trimEnd());

  const missing = Object.keys(fills).filter(placeholder => body.includes(placeholder));
  if (missing.length) {
    console.error(`\nStill to fill in: ${missing.join(", ")}`);
  }
  console.error(`Paste this into an agent whose workspace is ${tilde(workspace)}`);
}

async function where(argv) {
  const { flags } = parseFlags(argv);
  const workspace = resolveWorkspace(flags);
  console.log(workspace);
}

// 4. Forwarding, so every command in SKILL.md runs from the workspace root.

function forward(command, argv) {
  const { flags } = parseFlags(argv);
  const workspace = resolveWorkspace(flags);
  if (!isWorkspace(workspace)) {
    die(`no workspace at ${tilde(workspace)}; run: npx @frontierharness/eval`);
  }

  const script = SCRIPTS[command];
  const path = join(workspace, SCRIPTS_DIR, script);
  if (!existsSync(path)) die(`${script} is missing from ${tilde(workspace)}; re-run: npx @frontierharness/eval --force`);

  // Scripts are invoked through their interpreter so a lost executable bit or a
  // noexec mount cannot break the run.
  const runner = script.endsWith(".mjs") ? [process.execPath, path] : ["bash", path];
  const passthrough = dropFlag(argv, "--dir");
  const child = spawn(runner[0], [runner[1], ...passthrough], { cwd: workspace, stdio: "inherit" });
  child.on("error", error => die(`could not run ${script}: ${error.message}`));
  child.on("close", (code, signal) => process.exit(signal ? 1 : code ?? 1));
}

function dropFlag(argv, flag) {
  const kept = [];
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === flag) { index += 1; continue; }
    if (argv[index].startsWith(`${flag}=`)) continue;
    kept.push(argv[index]);
  }
  return kept;
}

// Shared helpers.

function resolveWorkspace(flags) {
  if (flags.dir) return resolve(flags.dir);
  // Inside a clone already, use it; otherwise a sibling folder of the current one.
  if (isWorkspace(process.cwd())) return process.cwd();
  return resolve(process.cwd(), DEFAULT_WORKSPACE);
}

function isWorkspace(dir) {
  return WORKSPACE_MARKERS.every(entry => existsSync(join(dir, entry)));
}

function parseFlags(argv) {
  const flags = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const raw = token.slice(2);
    const split = raw.indexOf("=");
    const name = split === -1 ? raw : raw.slice(0, split);
    const inline = split === -1 ? undefined : raw.slice(split + 1);
    if (BOOLEAN_FLAGS.has(name) && inline === undefined) flags[name] = true;
    else flags[name] = inline ?? argv[++index];
  }
  return { flags };
}

async function packageVersion() {
  const pkg = JSON.parse(await readFile(join(PKG_ROOT, "package.json"), "utf8"));
  return `v${pkg.version}`;
}

function tilde(path) {
  return path.startsWith(homedir()) ? path.replace(homedir(), "~") : path;
}

function usage() {
  console.log(usageText());
}

function usageText() {
  return `FrontierHarness Eval — benchmark your harness on the published tasks and runtime.

Usage: npx @frontierharness/eval [command] [options]

Commands:
  install (default)  Create the benchmark workspace and install the skill for your agents
  doctor             Check prerequisites: node, jq, runta CLI and auth, provider key
  prompt             Print the copy-paste prompt that drives the whole run
  provision          Freeze a golden checkpoint   (skill step 1-3)
  run                Run trials from fresh restores (skill step 4)
  normalize          Score the trials             (skill step 5)
  chart              Draw the comparison chart    (skill step 5)
  report             Build REPORT.md and index.html (skill step 6)
  where              Print the resolved workspace path

Install options:
  --dir PATH         Workspace location (default ./frontierharness-eval, or the current
                     directory when it already holds benchmark.json, results/ and tasks/)
  --agent LIST       cursor, claude, codex, or all / auto / none (default auto)
  --global           Install the skill into ~ instead of the workspace
  --copy             Copy the skill into each agent directory rather than symlinking
  --force            Overwrite workspace files and existing skill directories

Prompt options:
  --harness NAME  --repo URL  --commit SHA  --provider NAME  --build "STEPS"
  --smoke            Two tasks instead of the full 30-task sweep

provision, run, normalize, chart and report forward every other flag to the skill's own
scripts with the workspace as the working directory, so SKILL.md applies verbatim:
  npx @frontierharness/eval provision --runtime fh-build --checkpoint fh-golden-v1 \\
    --harness my-harness --repo https://github.com/acme/my-harness --commit 9f2c1ab
  npx @frontierharness/eval run --checkpoint fh-golden-v1 --harness my-harness \\
    --run-id 2026-09-02-myharness --out runs

Docs: https://frontierharness.org`;
}

function die(message) {
  console.error(message);
  process.exit(2);
}
