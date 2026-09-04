import { readFile, writeFile } from "node:fs/promises";

const evaluation = JSON.parse(await readFile(new URL("../results/eval-data.json", import.meta.url), "utf8"));
const iconData = Object.fromEntries(await Promise.all(["codex","pi","exo","deepseek","kot"].map(async name => {
  const source = await readFile(new URL(`../assets/harness-icons/${name}.svg`, import.meta.url));
  return [name, `data:image/svg+xml;base64,${source.toString("base64")}`];
})));
const rows = evaluation.harnesses;
const total = evaluation.overview.checkpoint_tasks;
const byName = name => rows.find(row => row.name === name);
const quality = [...rows].sort((a,b) => b.successful-a.successful || a.effective_cost_per_pass-b.effective_cost_per_pass)[0];
const balanced = byName("pi-responses");
const cost = [...rows].sort((a,b) => a.effective_cost_per_pass-b.effective_cost_per_pass || b.successful-a.successful)[0];
const speed = [...rows].sort((a,b) => a.median_duration_seconds-b.median_duration_seconds || b.successful-a.successful)[0];
const rate = row => `${(row.successful/total*100).toFixed(1)}%`;
const dollars = row => `$${row.effective_cost_per_pass.toFixed(2)}`;
const duration = row => `${Math.floor(row.median_duration_seconds/60)}m ${Math.round(row.median_duration_seconds%60)}s`;
const displayName = row => ({kot:"KOT",codex:"Codex",exo:"Exo Harness","dsh-minimal":"DSH Minimal","pi-responses":"Pi"}[row.name] ?? row.name);
const iconKind = row => ({kot:"kot",codex:"codex",exo:"exo","pi-responses":"pi"}[row.name] ?? "deepseek");
const cards = [
  {title:"Quality Leader",name:displayName(quality),metric:`${rate(quality)} pass rate · ${dollars(quality)} per task`,kind:iconKind(quality)},
  {title:"Balanced Pick",name:"Pi",metric:`${rate(balanced)} pass rate · ${dollars(balanced)} per task`,kind:"pi"},
  {title:"Cost Leader",name:displayName(cost),metric:`${dollars(cost)} per task · ${rate(cost)} pass rate`,kind:iconKind(cost)},
  {title:"Speed Leader",name:displayName(speed),metric:`${duration(speed)} median runtime · ${rate(speed)} pass rate`,kind:iconKind(speed)},
];

const icon = (kind,x,y) => `<image href="${iconData[kind]}" x="${x}" y="${y}" width="32" height="32"/>`;

const card = (item,index) => {
  const x = index%2*600;
  const y = Math.floor(index/2)*210;
  const divider = `${index%2 ? `<line x1="${x}" y1="${y}" x2="${x}" y2="${y+210}"/>` : ""}${index>1 ? `<line x1="${x}" y1="${y}" x2="${x+600}" y2="${y}"/>` : ""}`;
  return `${divider}${icon(item.kind,x+42,y+38)}<text x="${x+42}" y="${y+111}" class="title"><tspan font-weight="700">${item.title}:</tspan> ${item.name}</text><text x="${x+42}" y="${y+158}" class="metric">${item.metric}</text>`;
};

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="420" viewBox="0 0 1200 420" role="img" aria-label="FrontierHarness Eval leaders">
  <rect width="1200" height="420" fill="#08080d"/>
  <style>text{font-family:Arial,Helvetica,sans-serif}.title{fill:#ededed;font-size:24px}.metric{fill:#8491a8;font-family:"SFMono-Regular",Menlo,monospace;font-size:17px;letter-spacing:.3px}line{stroke:#24242c;stroke-width:1}</style>
  ${cards.map(card).join("")}
</svg>`;

await writeFile(new URL("../assets/frontier-harness-leaders.svg", import.meta.url), svg);
