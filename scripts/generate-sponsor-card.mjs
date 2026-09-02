import { readFile, writeFile } from "node:fs/promises";

const logo = (await readFile(new URL("../assets/runta-logo.png", import.meta.url))).toString("base64");
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="660" height="240" viewBox="0 0 660 240" role="img" aria-label="Sponsored by Runta">
  <rect width="660" height="240" rx="12" fill="#090b0c"/>
  <image href="data:image/png;base64,${logo}" x="48" y="48" width="144" height="144"/>
  <text x="222" y="143" fill="#ff8a31" font-family="Arial,Helvetica,sans-serif" font-size="62" font-weight="500" letter-spacing="18">RUNTA</text>
</svg>`;

await writeFile(new URL("../assets/runta-sponsor.svg", import.meta.url), svg);
