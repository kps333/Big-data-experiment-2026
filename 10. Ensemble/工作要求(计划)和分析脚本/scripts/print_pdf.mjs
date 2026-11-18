// 把 report/ensemble_report.html 通过 Chrome CDP 打印成 report/ensemble_report.pdf
// 用法: node scripts/print_pdf.mjs
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { fileURLToPath } from "node:url";
const BASE = resolve(fileURLToPath(new URL("..", import.meta.url)));
const HTML = resolve(BASE, "report/ensemble_report.html");
const PDF = resolve(BASE, "report/ensemble_report.pdf");

async function cdp() {
  const list = await (await fetch("http://127.0.0.1:9222/json/list")).json();
  const page = list.find((t) => t.type === "page");
  if (!page) throw new Error("no page target on :9222");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();
  await new Promise((res, rej) => {
    ws.addEventListener("open", res);
    ws.addEventListener("error", rej);
  });
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const { res, rej } = pending.get(m.id);
      pending.delete(m.id);
      m.error ? rej(new Error(JSON.stringify(m.error))) : res(m.result);
    }
  });
  const send = (method, params = {}) =>
    new Promise((res, rej) => {
      const myId = ++id;
      pending.set(myId, { res, rej });
      ws.send(JSON.stringify({ id: myId, method, params }));
    });
  return { send, close: () => ws.close() };
}

const { send, close } = await cdp();
await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: 816, height: 1056, deviceScaleFactor: 1, mobile: false,
});
await send("Page.navigate", { url: "file:///" + HTML.replace(/\\/g, "/") });
await new Promise((r) => setTimeout(r, 3000));
const { data } = await send("Page.printToPDF", {
  printBackground: true,
  preferCSSPageSize: true,
  paperWidth: 8.5,
  paperHeight: 11,
  marginTop: 0, marginBottom: 0, marginLeft: 0, marginRight: 0,
  displayHeaderFooter: false,
});
writeFileSync(PDF, Buffer.from(data, "base64"));
close();
console.log("@@DSH_RESULT@@" + JSON.stringify({ ok: true, bytes: readFileSync(PDF).length }));
