import { mkdir, readFile, writeFile } from "node:fs/promises";

const scatter = JSON.parse(await readFile(new URL("../results/scatter-data.json", import.meta.url), "utf8"));
const width = 1200;
const height = 630;
const plot = { x: 92, y: 52, width: 1020, height: 466 };
const labels = {"pi-responses":"Pi","oh-my-pi":"Oh My Pi","claude-code":"Claude Code",codex:"Codex",opencode:"OpenCode",hermes:"Hermes","kimi-code":"Kimi Code",exo:"Exo Harness","dsh-standard":"DSH Standard","dsh-ptc":"DSH PTC","dsh-minimal":"DSH Minimal","dsh-creator":"DSH Creator"};
const colors = {"pi-responses":"#262626","oh-my-pi":"#B35C00","claude-code":"#B9482C",codex:"#5142E8",opencode:"#7047C7",hermes:"#168A7D","kimi-code":"#187763",exo:"#59616B","dsh-standard":"#1267C4","dsh-ptc":"#357CC5","dsh-minimal":"#14589C","dsh-creator":"#3979B8"};
const shapes = {"pi-responses":"square","oh-my-pi":"diamond","claude-code":"diamond",codex:"circle",opencode:"square",hermes:"triangle","kimi-code":"circle",exo:"hexagon","dsh-standard":"square","dsh-ptc":"diamond","dsh-minimal":"circle","dsh-creator":"triangle"};
const placement = {
  codex:{dx:13,dy:4,anchor:"start"},
  "dsh-creator":{dx:13,dy:4,anchor:"start"},
  "claude-code":{dx:-13,dy:4,anchor:"end"},
  "pi-responses":{dx:13,dy:4,anchor:"start"},
  "dsh-ptc":{dx:13,dy:-10,anchor:"start"},
  "dsh-standard":{dx:13,dy:4,anchor:"start"},
  "oh-my-pi":{dx:13,dy:-9,anchor:"start"},
  "kimi-code":{dx:-13,dy:4,anchor:"end"},
  "dsh-minimal":{dx:13,dy:15,anchor:"start"},
  exo:{dx:13,dy:4,anchor:"start"},
  opencode:{dx:13,dy:4,anchor:"start"},
  hermes:{dx:-13,dy:4,anchor:"end"},
};
const px = percent => plot.x + percent / 100 * plot.width;
const py = percent => plot.y + (100 - percent) / 100 * plot.height;
const esc = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

function marker(shape, x, y, color) {
  const common = `fill="${color}" stroke="#FFFFFF" stroke-width="1.5"`;
  if (shape === "circle") return `<circle cx="${x}" cy="${y}" r="7" ${common}/>`;
  if (shape === "square") return `<rect x="${x-7}" y="${y-7}" width="14" height="14" ${common}/>`;
  if (shape === "diamond") return `<path d="M ${x} ${y-8} L ${x+8} ${y} L ${x} ${y+8} L ${x-8} ${y} Z" ${common}/>`;
  if (shape === "triangle") return `<path d="M ${x} ${y-8} L ${x+8} ${y+7} L ${x-8} ${y+7} Z" ${common}/>`;
  return `<path d="M ${x-7} ${y} L ${x-3.5} ${y-6.5} L ${x+3.5} ${y-6.5} L ${x+7} ${y} L ${x+3.5} ${y+6.5} L ${x-3.5} ${y+6.5} Z" ${common}/>`;
}

const gridX = scatter.x_ticks.map(tick => {
  const x = px(tick.x_percent);
  return `<line x1="${x}" y1="${plot.y}" x2="${x}" y2="${plot.y+plot.height}"/><text x="${x}" y="${plot.y+plot.height+28}" text-anchor="middle">$${tick.value}</text>`;
}).join("");
const gridY = scatter.y_ticks.map(tick => {
  const y = py(tick.y_percent);
  const rate = (tick.value / 30 * 100).toFixed(1);
  return `<line x1="${plot.x}" y1="${y}" x2="${plot.x+plot.width}" y2="${y}"/><text x="${plot.x-15}" y="${y+4}" text-anchor="end">${rate}%</text>`;
}).join("");
const frontier = scatter.frontier.map(point => `${px(point.x_percent)},${py(point.y_percent)}`).join(" ");
const points = scatter.points.map(item => {
  const x = px(item.x_percent);
  const y = py(item.y_percent);
  const p = placement[item.name];
  return `<g>${marker(shapes[item.name],x,y,colors[item.name])}<text class="point-label" x="${x+p.dx}" y="${y+p.dy}" fill="${colors[item.name]}" text-anchor="${p.anchor}">${esc(labels[item.name] ?? item.name)}</text></g>`;
}).join("");

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="1200" height="630" fill="#FAFAF8"/>
  <style>
    text{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .mono{font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace}
    .grid line{stroke:#E4E5E7;stroke-width:1}.grid text{fill:#777B82;font-size:12px}
    .point-label{font-size:14px;font-weight:600}
  </style>
  <g class="grid mono">${gridX}${gridY}</g>
  <polyline points="${frontier}" fill="none" stroke="#FF6418" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
  ${points}
  <text x="${plot.x+plot.width/2}" y="596" fill="#656A72" text-anchor="middle" font-size="14">Median cost per pass (failures included)</text>
  <text x="25" y="${plot.y+plot.height/2}" fill="#656A72" text-anchor="middle" font-size="14" transform="rotate(-90 25 ${plot.y+plot.height/2})">Pass rate</text>
</svg>`;

await mkdir(new URL("../assets/", import.meta.url), { recursive: true });
await writeFile(new URL("../assets/frontier-harness-light.svg", import.meta.url), svg);
