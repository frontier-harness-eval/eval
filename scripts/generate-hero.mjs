import { mkdir, readFile, writeFile } from "node:fs/promises";

const evaluation = JSON.parse(await readFile(new URL("../results/eval-data.json", import.meta.url), "utf8"));
const width = 1200;
const height = 630;
const plot = { x: 68, y: 32, width: 1110, height: 530 };
const labels = {"pi-responses":"Pi","oh-my-pi":"Oh My Pi","claude-code":"Claude Code",codex:"Codex",opencode:"OpenCode",hermes:"Hermes","kimi-code":"Kimi Code",exo:"Exo Harness","dsh-standard":"DSH Standard","dsh-ptc":"DSH PTC","dsh-minimal":"DSH Minimal","dsh-creator":"DSH Creator"};
const colors = {"pi-responses":"#f0f0f0","oh-my-pi":"#f2a777","claude-code":"#f0a57f",codex:"#9385ff",opencode:"#a978e7",hermes:"#a3a3a3","kimi-code":"#83d7c5",exo:"#d3d3d3","dsh-standard":"#75b8ed","dsh-ptc":"#75b8ed","dsh-minimal":"#75b8ed","dsh-creator":"#70b6ee"};
const shapes = {"pi-responses":"square","oh-my-pi":"diamond","claude-code":"diamond",codex:"circle",opencode:"square",hermes:"triangle","kimi-code":"circle",exo:"hexagon","dsh-standard":"square","dsh-ptc":"diamond","dsh-minimal":"circle","dsh-creator":"triangle"};
const totalTasks = evaluation.overview.checkpoint_tasks;
const points = evaluation.harnesses.map(item => ({name:item.name,cost:item.effective_cost_per_pass,passRate:item.successful/totalTasks*100,successful:item.successful}));
const xDomain = { min: 1, max: 22 };
const yDomain = { min: 49, max: 68 };
const xPercent = cost => Math.log(cost/xDomain.min)/Math.log(xDomain.max/xDomain.min)*100;
const yPercent = rate => (rate-yDomain.min)/(yDomain.max-yDomain.min)*100;
const px = percent => plot.x + percent/100*plot.width;
const py = percent => plot.y + (100-percent)/100*plot.height;
const esc = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const formatCost = cost => `$${cost.toFixed(2)}`;
const formatRate = rate => `${rate.toFixed(1)}%`;
const pointMetric = point => `${formatRate(point.passRate)} · ${formatCost(point.cost)}`;
const frontier = points.filter(point=>!points.some(candidate=>candidate.cost<=point.cost&&candidate.passRate>=point.passRate&&(candidate.cost<point.cost||candidate.passRate>point.passRate))).sort((a,b)=>a.cost-b.cost);

const harnessCount = evaluation.overview.harnesses;
const configurationCount = evaluation.overview.harness_configurations;
const evaluationCount = evaluation.overview.expected_cells;
if (totalTasks!==30 || harnessCount!==9 || configurationCount!==12 || evaluationCount!==360 || points.length!==configurationCount) {
  throw new Error("Canonical benchmark counts do not match the banner contract");
}

const fontSize = 13.5;
const metricFontSize = 11.5;
const markerRadius = 12;
const nameWidth = text => [...text].reduce((sum,char)=>sum+(char===" "?3.7:7.5),0);
const metricWidth = text => [...text].reduce((sum,char)=>sum+(char===" "?3.4:6.5),0);
const overlaps = (a,b,padding=0)=>a.left<b.right+padding&&a.right>b.left-padding&&a.top<b.bottom+padding&&a.bottom>b.top-padding;
const markerRects = new Map(points.map(point=>{const x=px(xPercent(point.cost));const y=py(yPercent(point.passRate));return [point.name,{left:x-markerRadius,right:x+markerRadius,top:y-markerRadius,bottom:y+markerRadius}]}));
const candidates = [
  {side:"right",position:"center",dx:15,dy:-2,anchor:"start"},
  {side:"right",position:"below",dx:15,dy:25,anchor:"start"},
  {side:"right",position:"above",dx:15,dy:-25,anchor:"start"},
  {side:"left",position:"center",dx:-15,dy:-2,anchor:"end"},
  {side:"left",position:"below",dx:-15,dy:25,anchor:"end"},
  {side:"left",position:"above",dx:-15,dy:-25,anchor:"end"},
  {side:"right",position:"far-below",dx:15,dy:48,anchor:"start"},
  {side:"right",position:"far-above",dx:15,dy:-48,anchor:"start"},
  {side:"left",position:"far-below",dx:-15,dy:48,anchor:"end"},
  {side:"left",position:"far-above",dx:-15,dy:-48,anchor:"end"},
  {side:"right",position:"detached",dx:64,dy:-2,anchor:"start"},
  {side:"left",position:"detached",dx:-64,dy:-2,anchor:"end"},
];
const leftFirst = [candidates[3],candidates[4],candidates[5],candidates[8],candidates[9],candidates[11],...candidates];

function labelRect(point,candidate) {
  const x=px(xPercent(point.cost));
  const y=py(yPercent(point.passRate));
  const text=Math.max(nameWidth(labels[point.name]??point.name),metricWidth(pointMetric(point)));
  const anchorX=x+candidate.dx;
  const baseline=y+candidate.dy;
  return {left:candidate.anchor==="start"?anchorX:anchorX-text,right:candidate.anchor==="start"?anchorX+text:anchorX,top:baseline-fontSize*.82,bottom:baseline+16+metricFontSize*.25};
}

const placed=[];
const placements=new Map();
const labelRects=new Map();
for (const point of points) {
  const order=point.name==="kimi-code"||point.name==="hermes"?leftFirst:candidates;
  let selected;
  for (const candidate of order) {
    const rect=labelRect(point,candidate);
    const hitsLabel=placed.some(item=>overlaps(rect,item.rect,4));
    const hitsPoint=[...markerRects].some(([name,marker])=>name!==point.name&&overlaps(rect,marker,3));
    const outside=rect.left<plot.x||rect.right>plot.x+plot.width||rect.top<plot.y||rect.bottom>plot.y+plot.height;
    if (!hitsLabel&&!hitsPoint&&!outside) { selected={candidate,rect}; break; }
  }
  if (!selected) throw new Error(`No collision-free label position for ${point.name}`);
  placements.set(point.name,selected.candidate);
  labelRects.set(point.name,selected.rect);
  placed.push({name:point.name,rect:selected.rect});
}

function marker(shape,x,y,color,size=9) {
  const common=`fill="${color}" stroke="#d8d8d8" stroke-width="1.2"`;
  if(shape==="circle")return `<circle cx="${x}" cy="${y}" r="${size}" ${common}/>`;
  if(shape==="square")return `<rect x="${x-size}" y="${y-size}" width="${size*2}" height="${size*2}" ${common}/>`;
  if(shape==="diamond")return `<path d="M ${x} ${y-size-1} L ${x+size+1} ${y} L ${x} ${y+size+1} L ${x-size-1} ${y} Z" ${common}/>`;
  if(shape==="triangle")return `<path d="M ${x} ${y-size-1} L ${x+size+1} ${y+size} L ${x-size-1} ${y+size} Z" ${common}/>`;
  return `<path d="M ${x-size} ${y} L ${x-size/2} ${y-size} L ${x+size/2} ${y-size} L ${x+size} ${y} L ${x+size/2} ${y+size} L ${x-size/2} ${y+size} Z" ${common}/>`;
}

const xTicks=[1,2,5,10,20];
const yTicks=[50,55,60,65];
const gridX=xTicks.map(value=>{const x=px(xPercent(value));return `<line x1="${x}" y1="${plot.y}" x2="${x}" y2="${plot.y+plot.height}"/><text x="${x}" y="${plot.y+plot.height+24}" text-anchor="middle">$${value}</text>`}).join("");
const gridY=yTicks.map(value=>{const y=py(yPercent(value));return `<line x1="${plot.x}" y1="${y}" x2="${plot.x+plot.width}" y2="${y}"/><text x="${plot.x-14}" y="${y+4}" text-anchor="end">${value}%</text>`}).join("");
const frontierLine=frontier.map(point=>`${px(xPercent(point.cost))},${py(yPercent(point.passRate))}`).join(" ");
const pointMarkup=points.map(point=>{const x=px(xPercent(point.cost));const y=py(yPercent(point.passRate));const p=placements.get(point.name);const rect=labelRects.get(point.name);const labelX=x+p.dx;const background=`<rect x="${rect.left-4}" y="${rect.top-3}" width="${rect.right-rect.left+8}" height="${rect.bottom-rect.top+6}" rx="2" fill="#020202"/>`;return `<g>${background}${marker(shapes[point.name],x,y,colors[point.name])}<text class="point-name" data-placement="${p.side}-${p.position}" x="${labelX}" y="${y+p.dy}" fill="${colors[point.name]}" text-anchor="${p.anchor}"><tspan x="${labelX}">${esc(labels[point.name]??point.name)}</tspan><tspan class="point-value" x="${labelX}" dy="16">${pointMetric(point)}</tspan></text></g>`}).join("");

const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="FrontierHarness Eval benchmark" shape-rendering="geometricPrecision" text-rendering="geometricPrecision">
  <rect width="1200" height="630" fill="#020202"/>
  <style>
    text{font-family:Arial,Helvetica,sans-serif}.mono,.axis,.point-value{font-family:"SFMono-Regular",Menlo,monospace}
    .grid line{stroke:#323232;stroke-width:1;stroke-dasharray:3 3}.grid text{fill:#ececec;font-family:"SFMono-Regular",Menlo,monospace;font-size:12px}
    .point-name{font-size:13.5px;font-weight:400}.point-value{fill:#c9c9c9;font-size:11.5px}
  </style>
  <g class="grid axis">${gridX}${gridY}</g>
  <path d="M ${plot.x} ${plot.y} V ${plot.y+plot.height} H ${plot.x+plot.width}" fill="none" stroke="#eeeeee" stroke-width="1.25"/>
  <polyline points="${frontierLine}" fill="none" stroke="#ff7a12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  ${pointMarkup}
  <text x="${plot.x+plot.width/2}" y="610" fill="#ececec" text-anchor="middle" class="mono" font-size="13.5">Median cost per task (log scale)</text>
  <text x="25" y="${plot.y+plot.height/2}" fill="#ececec" text-anchor="middle" class="mono" font-size="13" transform="rotate(-90 25 ${plot.y+plot.height/2})">Pass rate</text>
</svg>`;

await mkdir(new URL("../assets/",import.meta.url),{recursive:true});
await writeFile(new URL("../assets/frontier-harness-light.svg",import.meta.url),svg);

const svgBody=svg.slice(svg.indexOf(">")+1,svg.lastIndexOf("</svg>"));
const platformFrame=({pixelWidth,pixelHeight,viewY,viewHeight,label})=>`<svg xmlns="http://www.w3.org/2000/svg" width="${pixelWidth}" height="${pixelHeight}" viewBox="0 ${viewY} 1200 ${viewHeight}" role="img" aria-label="${label}" shape-rendering="geometricPrecision" text-rendering="geometricPrecision">
  <rect x="0" y="${viewY}" width="1200" height="${viewHeight}" fill="#020202"/>
  ${svgBody}
</svg>`;

await writeFile(new URL("../assets/frontier-harness-x.svg",import.meta.url),platformFrame({pixelWidth:1920,pixelHeight:1080,viewY:-22.5,viewHeight:675,label:"FrontierHarness Eval for X"}));
await writeFile(new URL("../assets/frontier-harness-linkedin.svg",import.meta.url),platformFrame({pixelWidth:1200,pixelHeight:627,viewY:1.5,viewHeight:627,label:"FrontierHarness Eval for LinkedIn"}));
