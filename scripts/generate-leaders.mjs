import { readFile, writeFile } from "node:fs/promises";

const evaluation = JSON.parse(await readFile(new URL("../results/eval-data.json", import.meta.url), "utf8"));
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
const cards = [
  {title:"Quality Leader",name:"Codex",metric:`${rate(quality)} pass rate · ${dollars(quality)} per task`,kind:"codex"},
  {title:"Balanced Pick",name:"Pi",metric:`${rate(balanced)} pass rate · ${dollars(balanced)} per task`,kind:"pi"},
  {title:"Cost Leader",name:"Exo Harness",metric:`${dollars(cost)} per task · ${rate(cost)} pass rate`,kind:"exo"},
  {title:"Speed Leader",name:"DSH Minimal",metric:`${duration(speed)} median runtime · ${rate(speed)} pass rate`,kind:"dsh"},
];

const icon = (kind,x,y) => {
  if (kind === "codex") return `<rect x="${x}" y="${y}" width="32" height="32" rx="7" fill="#fff"/><rect x="${x+3}" y="${y+3}" width="26" height="26" rx="6" fill="#766bff"/><text x="${x+16}" y="${y+21}" text-anchor="middle" fill="#fff" font-family="monospace" font-size="12" font-weight="700">›_</text>`;
  if (kind === "pi") return `<g transform="translate(${x} ${y})" fill="#f5f5f5"><path d="M0 0h24v16h-8v8H8v8H0V0Zm8 8v8h8V8H8Z"/><path d="M24 16h8v16h-8V16Z"/></g>`;
  if (kind === "exo") return `<circle cx="${x+16}" cy="${y+16}" r="16" fill="#292929"/><path d="M${x+9} ${y+9}l7 5 7-5-5 7 5 7-7-5-7 5 5-7-5-7Z" fill="#f2f2f2"/>`;
  return `<path d="M${x+1} ${y+17}c6 9 19 11 28 2-5 1-8-1-10-4 5 1 9-1 12-6-5 3-9 2-12-1-4 6-10 7-18 9Z" fill="#4d6bfe"/><circle cx="${x+24}" cy="${y+9}" r="2" fill="#4d6bfe"/>`;
};

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
