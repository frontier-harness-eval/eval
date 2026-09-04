import { mkdir, readFile, writeFile } from "node:fs/promises";

const evaluation = JSON.parse(await readFile(new URL("../results/eval-data.json", import.meta.url), "utf8"));
const labels = {"pi-responses":"Pi","oh-my-pi":"Oh My Pi","claude-code":"Claude Code",codex:"Codex",opencode:"OpenCode",hermes:"Hermes","kimi-code":"Kimi Code",exo:"Exo Harness","dsh-standard":"DSH Standard","dsh-ptc":"DSH PTC","dsh-minimal":"DSH Minimal","dsh-creator":"DSH Creator"};
const colors = {"pi-responses":"#f0f0f0","oh-my-pi":"#f2a777","claude-code":"#f0a57f",codex:"#9385ff",opencode:"#a978e7",hermes:"#a3a3a3","kimi-code":"#83d7c5",exo:"#d3d3d3","dsh-standard":"#75b8ed","dsh-ptc":"#75b8ed","dsh-minimal":"#75b8ed","dsh-creator":"#70b6ee"};
const harnesses = evaluation.harnesses;
const totalTasks = evaluation.overview.checkpoint_tasks;
const missing = harnesses.filter(item => !labels[item.name] || !colors[item.name]);
if (missing.length) throw new Error(`Unlabelled harness configurations: ${missing.map(item => item.name).join(", ")}`);

const esc = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const formatDuration = value => { const seconds = Math.round(value); const minutes = Math.floor(seconds/60); return minutes ? `${minutes}m ${seconds%60}s` : `${seconds}s`; };
const sortValue = (metric,value) => metric==="cache_hit_rate_typical" ? Math.round(value*1000) : metric==="median_duration_seconds" ? Math.round(value) : metric==="successful" ? value : Math.round(value*10000);
const panels = [
  {title:"Pass rate",metric:"successful",format:value=>`${(value/totalTasks*100).toFixed(1)}%`},
  {title:"Median cost per pass (failures excluded)",metric:"median_cost_per_success_normalized",format:value=>`$${value.toFixed(4)}`,ascending:true},
  {title:"Median cost per pass (failures included)",metric:"effective_cost_per_pass",format:value=>`$${value.toFixed(4)}`,ascending:true},
  {title:"Median cache hit rate per successful task",metric:"cache_hit_rate_typical",format:value=>`${(value*100).toFixed(1)}%`},
  {title:"Median time per successful task",metric:"median_duration_seconds",format:formatDuration,ascending:true},
];

const width = 1200;
const pad = 24;
const gap = 20;
const halfWidth = (width-pad*2-gap)/2;
const fullWidth = width-pad*2;
const panelPad = 20;
const headerHeight = 48;
const listTop = 60;
const rowHeight = 24;
const barHeight = 14;
const rankColumn = 20;
const nameColumn = 105;
const valueColumn = 68;
const columnGap = 9;
const panelHeight = listTop+harnesses.length*rowHeight+16;
const height = pad*2+panelHeight*3+gap*2;

function rankRows({metric,format,ascending=false}) {
  const rows = harnesses
    .map(item => ({item,value:item[metric]}))
    .filter(row => typeof row.value === "number")
    .sort((a,b) => {
      const primary = sortValue(metric,a.value)-sortValue(metric,b.value);
      if (primary !== 0) return ascending ? primary : -primary;
      return b.item.successful-a.item.successful || labels[a.item.name].localeCompare(labels[b.item.name]);
    });
  const max = metric==="successful" ? totalTasks : Math.max(...rows.map(row => row.value),1);
  return rows.map((row,index) => ({...row,index,max,formatted:format(row.value)}));
}

function panel(config,x,y,panelWidth) {
  const content = panelWidth-panelPad*2;
  const barWidth = content-rankColumn-nameColumn-valueColumn-columnGap*3;
  const barX = x+panelPad+rankColumn+nameColumn+columnGap*2;
  const rows = rankRows(config);
  const list = rows.map(({item,value,index,max,formatted}) => {
    const center = y+listTop+index*rowHeight+rowHeight/2;
    const baseline = center+3.8;
    const fill = Math.max(value/max*barWidth,2);
    return `<text class="rank" x="${x+panelPad}" y="${baseline}">${String(index+1).padStart(2,"0")}</text>`
      + `<text class="name" x="${x+panelPad+rankColumn+columnGap}" y="${baseline}">${esc(labels[item.name])}</text>`
      + `<rect class="track" x="${barX}" y="${center-barHeight/2}" width="${barWidth}" height="${barHeight}"/>`
      + `<rect x="${barX}" y="${center-barHeight/2}" width="${fill.toFixed(2)}" height="${barHeight}" fill="${colors[item.name]}"/>`
      + `<text class="value" x="${x+panelWidth-panelPad}" y="${baseline}" text-anchor="end">${esc(formatted)}</text>`;
  }).join("");
  const excluded = harnesses.length-rows.length;
  const note = excluded ? `<text class="note" x="${x+panelPad}" y="${y+panelHeight-14}">${excluded} harness excluded: metric unavailable</text>` : "";
  return `<rect x="${x}" y="${y}" width="${panelWidth}" height="${panelHeight}" rx="12" fill="#0a0a0a" stroke="#242424"/>`
    + `<text class="title" x="${x+panelPad}" y="${y+31}">${esc(config.title)}</text>`
    + `<line x1="${x+panelPad}" y1="${y+headerHeight}" x2="${x+panelWidth-panelPad}" y2="${y+headerHeight}" stroke="#1c1c1c"/>`
    + list+note;
}

const grid = panels.map((config,index) => index<4
  ? panel(config,pad+index%2*(halfWidth+gap),pad+Math.floor(index/2)*(panelHeight+gap),halfWidth)
  : panel(config,pad,pad+2*(panelHeight+gap),fullWidth)).join("");

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="FrontierHarness Eval rankings: pass rate, median cost per pass with and without failures, median cache hit rate, and median time across twelve harness configurations" shape-rendering="geometricPrecision" text-rendering="geometricPrecision">
  <rect width="${width}" height="${height}" fill="#020202"/>
  <style>
    text{font-family:Arial,Helvetica,sans-serif}
    .title{fill:#ededed;font-size:16px}
    .name{fill:#b9b9b9;font-size:11px}
    .rank,.value,.note{font-family:"SFMono-Regular",Menlo,monospace}
    .rank{fill:#5a5a5a;font-size:9px}
    .value{fill:#ededed;font-size:11px}
    .note{fill:#706a63;font-size:9px}
    .track{fill:#1a1a1a}
  </style>
  ${grid}
</svg>`;

await mkdir(new URL("../assets/",import.meta.url),{recursive:true});
await writeFile(new URL("../assets/frontier-harness-rankings.svg",import.meta.url),svg);
