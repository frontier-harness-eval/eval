import { websiteCost as calculateWebsiteCost } from "./website-cost.mjs";
// Plot a candidate harness against the published FrontierHarness baselines:
// a reference-style pass-rate versus cost scatter with a starred candidate.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const args = parseArgs(process.argv.slice(2));
const runDir = args.run ?? die("usage: generate-chart.mjs --run runs/<run-id> [--baseline results/eval-data.json]");
const baselinePath = args.baseline ?? "results/eval-data.json";

const labels = {
  "pi-responses": "Pi", "oh-my-pi": "Oh My Pi", "claude-code": "Claude Code", codex: "Codex",
  opencode: "OpenCode", hermes: "Hermes", "kimi-code": "Kimi Code", exo: "Exo Harness",
  "dsh-standard": "DSH Standard", "dsh-ptc": "DSH PTC", "dsh-minimal": "DSH Minimal",
  "dsh-creator": "DSH Creator",
};

const baseline = await readJson(baselinePath, `baseline not found at ${baselinePath}; pass --baseline <path to eval-data.json>`);
const candidate = await readJson(join(runDir, "candidate.json"), `candidate.json not found in ${runDir}; run normalize-results.mjs first`);
const observedAudit = await readFile(join(runDir, "observed-cost-audit.json"), "utf8").then(JSON.parse).catch(() => null);
const comparable = candidate.comparable === true;
const displayRank = comparable || args["display-rank"] === "true";

const points = [
  ...baseline.harnesses.map(item => ({
    name: item.name,
    label: labels[item.name] ?? item.name,
    passRate: item.pass_rate,
    cost: websiteCost(item),
    isCandidate: false,
  })),
  {
    name: "candidate",
    label: candidate.label,
    passRate: candidate.pass_rate,
    cost: websiteCost(candidate),
    isCandidate: true,
  },
];

const colors = {"pi-responses":"#f0f0f0","oh-my-pi":"#f2a777","claude-code":"#f0a57f",codex:"#9385ff",opencode:"#a978e7",hermes:"#a3a3a3","kimi-code":"#83d7c5",exo:"#d3d3d3","dsh-standard":"#75b8ed","dsh-ptc":"#75b8ed","dsh-minimal":"#75b8ed","dsh-creator":"#70b6ee"};
const shapes = {"pi-responses":"square","oh-my-pi":"diamond","claude-code":"diamond",codex:"circle",opencode:"square",hermes:"triangle","kimi-code":"circle",exo:"hexagon","dsh-standard":"square","dsh-ptc":"diamond","dsh-minimal":"circle","dsh-creator":"triangle"};

const accent = "#ff7a12";
colors.candidate = accent;
shapes.candidate = "star";
const eligible = points.filter(point => !point.isCandidate || displayRank);
const plotted = eligible.filter(point => Number.isFinite(point.cost) && point.cost > 0 && Number.isFinite(point.passRate));
const width = 1344;
const height = 660;
const plot = { x: 102, y: 96, width: 1200, height: 460 };
const costs = plotted.map(point => point.cost);
const rates = plotted.map(point => point.passRate);
const xDomain = { min: Math.min(0.83, ...costs.map(cost => cost / 1.15)), max: Math.max(23, ...costs.map(cost => cost * 1.15)) };
const rateLow = Math.min(...rates, 0.5);
const rateHigh = Math.max(...rates, 2/3);
const rateSpan = Math.max(rateHigh - rateLow, 0.1);
const yDomain = { min: Math.max(0, rateLow - rateSpan * 0.08), max: Math.min(1, rateHigh + rateSpan * 0.08) };
const px = cost => plot.x + Math.log(cost/xDomain.min)/Math.log(xDomain.max/xDomain.min)*plot.width;
const py = rate => plot.y + (yDomain.max-rate)/(yDomain.max-yDomain.min)*plot.height;
const esc = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', '&quot;');
const money = value => `$${value.toFixed(2)}`;
const percent = value => `${(value*100).toFixed(1)}%`;
const metric = point => `${percent(point.passRate)} · ${money(point.cost)}`;
const frontierEligible = plotted.filter(point => !point.isCandidate || comparable);
const frontier = frontierEligible.filter(point => !frontierEligible.some(other => other.cost <= point.cost && other.passRate >= point.passRate && (other.cost < point.cost || other.passRate > point.passRate))).sort((a,b) => a.cost-b.cost);
function marker(shape,x,y,color,size=6.5) {
  const common=`fill="${color}" stroke="#c4c4c4" stroke-width="1.1"`;
  if(shape === "star") {
    const vertices=Array.from({length:10},(_,i)=>{const a=-Math.PI/2+i*Math.PI/5;const r=i%2?size*.45:size;return `${x+Math.cos(a)*r},${y+Math.sin(a)*r}`;}).join(" ");
    return `<polygon points="${vertices}" ${common}/>`;
  }
  if(shape === "circle") return `<circle cx="${x}" cy="${y}" r="${size}" ${common}/>`;
  if(shape === "square") return `<rect x="${x-size}" y="${y-size}" width="${size*2}" height="${size*2}" ${common}/>`;
  const vertices = shape === "diamond" ? [[0,-1],[1,0],[0,1],[-1,0]] : shape === "triangle" ? [[0,-1],[1,1],[-1,1]] : [[-1,0],[-.5,-1],[.5,-1],[1,0],[.5,1],[-.5,1]];
  return `<polygon points="${vertices.map(([dx,dy])=>`${x+dx*size},${y+dy*size}`).join(" ")}" ${common}/>`;
}
const overlaps=(a,b,p=4)=>a.left<b.right+p&&a.right>b.left-p&&a.top<b.bottom+p&&a.bottom>b.top-p;
const obstacles=plotted.map(point=>({left:px(point.cost)-10,right:px(point.cost)+10,top:py(point.passRate)-10,bottom:py(point.passRate)+10}));
const placed=[];
// Give the candidate first choice of label position and draw its marker last.
const annotations=[...plotted].sort((a,b)=>Number(b.isCandidate)-Number(a.isCandidate)).map(point=>{
  const x=px(point.cost), y=py(point.passRate);
  const w=Math.max(point.label.length*7.5,metric(point).length*7.2);
  const sides=point.name === "kimi-code" || point.name === "hermes" ? [-1,1] : [1,-1];
  let selected;
  for(const dy of [-3,-34,27,55,-62,83,-90,111,-118,139,-146]) {
    for(const side of sides) {
      const lx=x+side*13;
      const rect={left:side===1?lx:lx-w,right:side===1?lx+w:lx,top:y+dy-12,bottom:y+dy+20};
      if(rect.left<plot.x+2||rect.right>plot.x+plot.width-2||rect.top<plot.y||rect.bottom>plot.y+plot.height)continue;
      if(placed.some(other=>overlaps(rect,other))||obstacles.some(other=>overlaps(rect,other,2)))continue;
      selected={lx,ly:y+dy,anchor:side===1?"start":"end",rect};break;
    }
    if(selected)break;
  }
  if(!selected)throw new Error(`No collision-free label placement for ${point.label}; enlarge the plot or extend label positions`);
  placed.push(selected.rect);
  const {lx,ly,anchor}=selected;
  return `<text class="point-name" x="${lx}" y="${ly}" fill="${colors[point.name]??"#bcbcbc"}" text-anchor="${anchor}"><tspan x="${lx}">${esc(point.label)}</tspan><tspan class="point-value" x="${lx}" dy="18">${metric(point)}</tspan></text>`;
}).join("");
const dots=[...plotted].sort((a,b)=>Number(a.isCandidate)-Number(b.isCandidate)).map(point=>{
  const x=px(point.cost),y=py(point.passRate);
  return (point.isCandidate?`<circle cx="${x}" cy="${y}" r="16" fill="none" stroke="${accent}" stroke-opacity=".4"/>`:"")+marker(shapes[point.name]??"circle",x,y,colors[point.name]??"#bcbcbc",point.isCandidate?12:6.5);
}).join("");
let legendX=48,legendY=29;
const legendOrder=["codex","dsh-creator","claude-code","pi-responses","dsh-ptc","dsh-standard","oh-my-pi","kimi-code","dsh-minimal","exo","opencode","hermes","candidate"];
const legend=legendOrder.map(name=>points.find(point=>point.name===name)).filter(Boolean).map(point=>{
  const label=point.isCandidate?"Third-party harness":"";
  const text=label||point.label;
  const itemWidth=text.length*7.4+30;
  if(legendX+itemWidth>width-35){legendX=48;legendY+=25;}
  const item=marker(shapes[point.name],legendX,legendY-4,colors[point.name],point.isCandidate?8:4.7)+`<text class="legend" x="${legendX+11}" y="${legendY}">${esc(text)}</text>`;
  legendX+=itemWidth;return item;
}).join("");
const ticks = [1, 2, 5, 10, 20].filter(value => value >= xDomain.min && value <= xDomain.max);
const gridX=ticks.map(value=>`<line x1="${px(value)}" y1="${plot.y}" x2="${px(value)}" y2="${plot.y+plot.height}"/><text x="${px(value)}" y="${plot.y+plot.height+27}" text-anchor="middle">$${value}</text>`).join("");
const gridY=Array.from({length:4},(_,i)=>rateLow+(rateHigh-rateLow)*i/3).map(value=>`<line x1="${plot.x}" y1="${py(value)}" x2="${plot.x+plot.width}" y2="${py(value)}"/><text x="${plot.x-13}" y="${py(value)+5}" text-anchor="end">${percent(value)}</text>`).join("");
const note = !comparable && displayRank
  ? "Candidate shown provisionally; evaluation conditions differ. Candidate cost may be incomplete (see report coverage); excluded from baseline frontier."
  : !comparable
  ? `${candidate.label}: ${percent(candidate.pass_rate)} · ${Number.isFinite(websiteCost(candidate))?money(websiteCost(candidate)):"cost unavailable"} · ${candidate.completed}/${candidate.expected} tasks scored. ${candidate.completed<candidate.expected?"Subset":"Methodology differs"}; excluded from plot; not ranked.`
  : !plotted.some(point=>point.isCandidate) ? `${candidate.label}: cost unavailable; candidate omitted from plot.` : `${candidate.label} · Third-party harness under evaluation`;
const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(candidate.label)} versus FrontierHarness baselines: pass rate and median cost per task">
<rect width="${width}" height="${height}" fill="#000"/>
<style>
text{font-family:Arial,Helvetica,sans-serif}.legend,.axis,.point-value,.grid text,.note{font-family:Menlo,Consolas,monospace}
.legend{font-size:11px;fill:#b5b5b5}.grid line{stroke:#333;stroke-dasharray:4 2;stroke-width:1}.grid text{fill:#ccc;font-size:15px}
.point-name{font-size:14px}.point-value{fill:#bcbcbc;font-size:12px}.axis{fill:#ccc;font-size:15px}.note{fill:#aaa;font-size:11px}
</style>
${legend}
<g class="grid">${gridX}${gridY}</g>
<path d="M ${plot.x} ${plot.y} V ${plot.y+plot.height} H ${plot.x+plot.width}" fill="none" stroke="#ccc" stroke-width="1.2"/>
<polyline points="${frontier.map(point=>`${px(point.cost)},${py(point.passRate)}`).join(" ")}" fill="none" stroke="${accent}" stroke-width="2.2"/>
${annotations}${dots}
<text class="axis" x="${plot.x+plot.width/2}" y="613" text-anchor="middle">Median cost per task</text>
<text class="axis" transform="translate(49 ${plot.y+plot.height/2}) rotate(-90)" text-anchor="middle">Pass rate</text>
${marker("star",49,642,accent,8)}<text class="note" x="65" y="646">${esc(note)}</text>
</svg>`;
const reportDir=join(runDir,"report");
await mkdir(reportDir,{recursive:true});
await writeFile(join(reportDir,"chart.svg"),svg);
console.log(`wrote ${join(reportDir,"chart.svg")}`);

async function readJson(path, message) {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch {
    return die(message);
  }
}

function parseArgs(argv) {
  const parsed = {};
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index].startsWith("--")) parsed[argv[index].slice(2)] = argv[index + 1];
  }
  return parsed;
}

function die(message) {
  console.error(message);
  process.exit(2);
}

// Website chart compatibility: the public label differs from the accounting field.
function websiteCost(record) {
  return calculateWebsiteCost(record, record === candidate ? observedAudit : null);
}
