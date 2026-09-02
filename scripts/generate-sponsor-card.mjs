import { readFile, writeFile } from "node:fs/promises";

const logo = (await readFile(new URL("../assets/runta-logo.png", import.meta.url))).toString("base64");
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="128" viewBox="0 0 360 128" role="img" aria-label="Sponsored by Runta">
  <rect width="360" height="128" rx="8" fill="#090b0c"/>
  <image href="data:image/png;base64,${logo}" x="-12" y="0" width="128" height="128"/>
  <text x="94" y="83" fill="#ff8a31" font-family="Arial,Helvetica,sans-serif" font-size="46" font-weight="500" letter-spacing="12">RUNTA</text>
</svg>`;

await writeFile(new URL("../assets/runta-sponsor.svg", import.meta.url), svg);
