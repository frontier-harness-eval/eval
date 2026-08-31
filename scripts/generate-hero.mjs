import { mkdir, readFile, writeFile } from "node:fs/promises";

const evaluation = JSON.parse(await readFile(new URL("../results/eval-data.json", import.meta.url), "utf8"));
const width = 1200;
const height = 630;
const plot = { x: 92, y: 52, width: 1020, height: 466 };
const labels = {"pi-responses":"Pi","oh-my-pi":"Oh My Pi","claude-code":"Claude Code",codex:"Codex",opencode:"OpenCode",hermes:"Hermes","kimi-code":"Kimi Code",exo:"Exo Harness","dsh-standard":"DSH Standard","dsh-ptc":"DSH PTC","dsh-minimal":"DSH Minimal","dsh-creator":"DSH Creator"};
const colors = {"pi-responses":"#262626","oh-my-pi":"#B35C00","claude-code":"#B9482C",codex:"#5142E8",opencode:"#7047C7",hermes:"#168A7D","kimi-code":"#187763",exo:"#59616B","dsh-standard":"#1267C4","dsh-ptc":"#357CC5","dsh-minimal":"#14589C","dsh-creator":"#3979B8"};
const shapes = {"pi-responses":"square","oh-my-pi":"diamond","claude-code":"diamond",codex:"circle",opencode:"square",hermes:"triangle","kimi-code":"circle",exo:"hexagon","dsh-standard":"square","dsh-ptc":"diamond","dsh-minimal":"circle","dsh-creator":"triangle"};
const points = evaluation.harnesses.map(item=>({name:item.name,successful:item.successful,cost:item.effective_cost_per_pass}));
const totalTasks = evaluation.overview.checkpoint_tasks;
const xMin = Math.min(...points.map(point => point.cost));
const xMax = Math.max(...points.map(point => point.cost));
const yMin = Math.min(...points.map(point => point.successful));
const yMax = Math.max(...points.map(point => point.successful));
const xPercent = cost => 8 + Math.log(cost/xMin)/Math.log(xMax/xMin)*84;
const yPercent = successful => 8 + (successful-yMin)/(yMax-yMin)*84;
const frontierPoints = points.filter(point=>!points.some(candidate=>candidate.cost<=point.cost&&candidate.successful>=point.successful&&(candidate.cost<point.cost||candidate.successful>point.successful))).sort((a,b)=>a.cost-b.cost);
const px = percent => plot.x + percent / 100 * plot.width;
const py = percent => plot.y + (100 - percent) / 100 * plot.height;
const esc = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
const fontSize = 13;
const markerRadius = 9;
const textWidth = text => [...text].reduce((width,char)=>width+(char===" "?3.6:7.15),0);
const overlaps = (a,b,padding=0)=>a.left<b.right+padding&&a.right>b.left-padding&&a.top<b.bottom+padding&&a.bottom>b.top-padding;
const markerRects = new Map(points.map(point=>{
  const x=px(xPercent(point.cost));
  const y=py(yPercent(point.successful));
  return [point.name,{left:x-markerRadius,right:x+markerRadius,top:y-markerRadius,bottom:y+markerRadius}];
}));
const candidates = [
  {side:"right",vertical:"center",dx:13,dy:4,anchor:"start"},
  {side:"right",vertical:"below",dx:13,dy:23,anchor:"start"},
  {side:"right",vertical:"above",dx:13,dy:-13,anchor:"start"},
  {side:"left",vertical:"center",dx:-13,dy:4,anchor:"end"},
  {side:"left",vertical:"below",dx:-13,dy:23,anchor:"end"},
  {side:"left",vertical:"above",dx:-13,dy:-13,anchor:"end"},
];
const leftFirstCandidates = [candidates[3],candidates[1],candidates[2],candidates[0],candidates[4],candidates[5]];

function labelRect(point,candidate){
  const x=px(xPercent(point.cost));
  const y=py(yPercent(point.successful));
  const width=textWidth(labels[point.name]??point.name);
  const anchorX=x+candidate.dx;
  const baseline=y+candidate.dy;
  return {
    left:candidate.anchor==="start"?anchorX:anchorX-width,
    right:candidate.anchor==="start"?anchorX+width:anchorX,
    top:baseline-fontSize*.82,
    bottom:baseline+fontSize*.25,
  };
}

const placedLabels=[];
const placements=new Map();
for(const point of points){
  let selected=null;
  const pointCandidates=point.name==="kimi-code"||point.name==="hermes"?leftFirstCandidates:candidates;
  for(const candidate of pointCandidates){
    const rect=labelRect(point,candidate);
    const hitsLabel=placedLabels.some(placed=>overlaps(rect,placed.rect,4));
    const hitsPoint=[...markerRects].some(([name,marker])=>name!==point.name&&overlaps(rect,marker,3));
    const outside=rect.left<8||rect.right>width-8||rect.top<8||rect.bottom>plot.y+plot.height;
    if(!hitsLabel&&!hitsPoint&&!outside){selected={candidate,rect};break}
  }
  if(!selected)throw new Error(`No collision-free label position for ${point.name}`);
  placements.set(point.name,selected.candidate);
  placedLabels.push({name:point.name,rect:selected.rect});
}

function marker(shape, x, y, color) {
  const common = `fill="${color}" stroke="#FFFFFF" stroke-width="1.5"`;
  if (shape === "circle") return `<circle cx="${x}" cy="${y}" r="7" ${common}/>`;
  if (shape === "square") return `<rect x="${x-7}" y="${y-7}" width="14" height="14" ${common}/>`;
  if (shape === "diamond") return `<path d="M ${x} ${y-8} L ${x+8} ${y} L ${x} ${y+8} L ${x-8} ${y} Z" ${common}/>`;
  if (shape === "triangle") return `<path d="M ${x} ${y-8} L ${x+8} ${y+7} L ${x-8} ${y+7} Z" ${common}/>`;
  return `<path d="M ${x-7} ${y} L ${x-3.5} ${y-6.5} L ${x+3.5} ${y-6.5} L ${x+7} ${y} L ${x+3.5} ${y+6.5} L ${x-3.5} ${y+6.5} Z" ${common}/>`;
}

const xTicks = [1,2,5,10,20];
const gridX = xTicks.map(value => {
  const x = px(xPercent(value));
  return `<line x1="${x}" y1="${plot.y}" x2="${x}" y2="${plot.y+plot.height}"/><text x="${x}" y="${plot.y+plot.height+28}" text-anchor="middle">$${value}</text>`;
}).join("");
const yTicks = Array.from({length:4},(_,index)=>yMin+(yMax-yMin)*index/3);
const gridY = yTicks.map(value => {
  const y = py(yPercent(value));
  const rate = (value / totalTasks * 100).toFixed(1);
  return `<line x1="${plot.x}" y1="${y}" x2="${plot.x+plot.width}" y2="${y}"/><text x="${plot.x-15}" y="${y+4}" text-anchor="end">${rate}%</text>`;
}).join("");
const frontier = frontierPoints.map(point => `${px(xPercent(point.cost))},${py(yPercent(point.successful))}`).join(" ");
const pointMarkup = points.map(item => {
  const x = px(xPercent(item.cost));
  const y = py(yPercent(item.successful));
  const p = placements.get(item.name);
  return `<g>${marker(shapes[item.name],x,y,colors[item.name])}<text class="point-label" data-placement="${p.side}-${p.vertical}" x="${x+p.dx}" y="${y+p.dy}" fill="${colors[item.name]}" text-anchor="${p.anchor}">${esc(labels[item.name] ?? item.name)}</text></g>`;
}).join("");

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="1200" height="630" fill="#FFFFFF"/>
  <style>
    text{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .mono{font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace}
    .grid line{stroke:#E4E5E7;stroke-width:1}.grid text{fill:#777B82;font-size:12px}
    .point-label{font-size:13px;font-weight:600}
  </style>
  <g class="grid mono">${gridX}${gridY}</g>
  <polyline points="${frontier}" fill="none" stroke="#FF6418" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
  ${pointMarkup}
  <text x="${plot.x+plot.width/2}" y="596" fill="#656A72" text-anchor="middle" font-size="14">Median cost per pass (failures included)</text>
  <text x="25" y="${plot.y+plot.height/2}" fill="#656A72" text-anchor="middle" font-size="14" transform="rotate(-90 25 ${plot.y+plot.height/2})">Pass rate</text>
</svg>`;

await mkdir(new URL("../assets/", import.meta.url), { recursive: true });
await writeFile(new URL("../assets/frontier-harness-light.svg", import.meta.url), svg);
