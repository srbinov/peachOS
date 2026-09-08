// Render a Lottie loop to a grid sprite-sheet PNG. See README.md.
//   node bake.mjs <input.json> <output.png> [frames=40] [cols=8] [cellW=400]
// Writes <output>.png and <output>.json ({frames,cols,rows,cellW,cellH,durationMs}).
import fs from 'fs';
import { createRequire } from 'module';
import { JSDOM } from 'jsdom';
import pkg from 'canvas';
const { createCanvas, Image } = pkg;
const require = createRequire(import.meta.url);

const dom = new JSDOM('<!DOCTYPE html><body></body>', { pretendToBeVisual: true });
global.window = dom.window;
global.document = dom.window.document;
try { global.Image = Image; } catch { /* getter-only on some node builds */ }
try { global.HTMLCanvasElement = dom.window.HTMLCanvasElement; } catch { /* ignore */ }
// route DOM canvas creation to node-canvas
const origCreate = dom.window.document.createElement.bind(dom.window.document);
dom.window.document.createElement = (name) =>
    name === 'canvas' ? createCanvas(32, 32) : origCreate(name);

const lottie = require('lottie-web');

const [inPath, outPath, framesArg, colsArg, cellWArg] = process.argv.slice(2);
const FRAMES = Number(framesArg) || 40;
const COLS = Number(colsArg) || 8;
const CELL_W = Number(cellWArg) || 360;
const ROWS = Math.ceil(FRAMES / COLS);

const data = JSON.parse(fs.readFileSync(inPath, 'utf8'));
const scale = CELL_W / data.w;
const renderW = Math.round(data.w * scale);
const renderH = Math.round(data.h * scale);

const canvas = createCanvas(renderW, renderH);
const ctx = canvas.getContext('2d');

const anim = lottie.loadAnimation({
    renderer: 'canvas',
    loop: false,
    autoplay: false,
    animationData: JSON.parse(JSON.stringify(data)),
    rendererSettings: { context: ctx, clearCanvas: true },
});

const totalFrames = anim.getDuration(true);
const rendered = [];
let minX = renderW, minY = renderH, maxX = 0, maxY = 0;

for (let i = 0; i < FRAMES; i++) {
    const f = (i / FRAMES) * totalFrames;
    anim.goToAndStop(f, true);
    const img = ctx.getImageData(0, 0, renderW, renderH);
    rendered.push(img);
    const d = img.data;
    for (let y = 0; y < renderH; y++)
        for (let x = 0; x < renderW; x++)
            if (d[(y * renderW + x) * 4 + 3] > 8) {
                if (x < minX) minX = x;
                if (x > maxX) maxX = x;
                if (y < minY) minY = y;
                if (y > maxY) maxY = y;
            }
}

minX = Math.max(0, minX - 1); minY = Math.max(0, minY - 1);
maxX = Math.min(renderW - 1, maxX + 1); maxY = Math.min(renderH - 1, maxY + 1);
const cropW = maxX - minX + 1;
const cropH = maxY - minY + 1;
console.log(`render ${renderW}x${renderH}  crop ${cropW}x${cropH} @ (${minX},${minY})  src frames ${totalFrames} -> ${FRAMES}`);

const sheet = createCanvas(cropW * COLS, cropH * ROWS);
const sctx = sheet.getContext('2d');
const tmp = createCanvas(renderW, renderH);
const tctx = tmp.getContext('2d');
for (let i = 0; i < FRAMES; i++) {
    tctx.putImageData(rendered[i], 0, 0);
    const col = i % COLS, row = Math.floor(i / COLS);
    sctx.drawImage(tmp, minX, minY, cropW, cropH, col * cropW, row * cropH, cropW, cropH);
}
fs.writeFileSync(outPath, sheet.toBuffer('image/png'));

const meta = {
    frames: FRAMES, cols: COLS, rows: ROWS,
    cellW: cropW, cellH: cropH,
    durationMs: Math.round(((data.op - data.ip) / data.fr) * 1000),
};
fs.writeFileSync(outPath.replace(/\.png$/, '.json'), JSON.stringify(meta, null, 2) + '\n');
console.log('wrote', outPath, JSON.stringify(meta), 'sheet', sheet.width + 'x' + sheet.height);
