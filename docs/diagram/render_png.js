// node docs/diagram/render_png.js docs/diagram/progress.excalidraw docs/diagram/progress.png  (needs Playwright from the AIOS animated-diagrams scripts and internet for the Excalidraw library)
const path = require('path'), fs = require('fs');
const { chromium } = require('C:/Users/alexg/OneDrive/Desktop/Smoothr AIOS/scripts/animated-diagrams/node_modules/playwright');
(async () => {
  const [inp, out] = process.argv.slice(2);
  const scene = JSON.parse(fs.readFileSync(inp, 'utf8'));
  const b = await chromium.launch(); const p = await b.newPage();
  p.on('pageerror', e => console.log('ERR', e.message));
  await p.setContent(`<html><body style="margin:0;background:#fff"><div id=o></div>
<script src="https://unpkg.com/react@18.3.1/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@excalidraw/excalidraw@0.17.6/dist/excalidraw.production.min.js"></script></body></html>`);
  await p.waitForFunction(() => window.ExcalidrawLib, null, { timeout: 60000 });
  const box = await p.evaluate(async (scene) => {
    const svg = await ExcalidrawLib.exportToSvg({ elements: scene.elements, appState: { ...scene.appState, exportBackground: true, exportScale: 1 }, files: {} });
    document.getElementById('o').appendChild(svg);
    await document.fonts.ready; await new Promise(r => setTimeout(r, 1500));
    const r = svg.getBoundingClientRect(); return { w: Math.ceil(r.width), h: Math.ceil(r.height) };
  }, scene);
  await p.setViewportSize({ width: box.w, height: box.h });
  await (await p.$('#o svg')).screenshot({ path: out });
  await b.close(); console.log(out, box);
})();
