// Static file server for the SDC-V frontend with a same-origin proxy to the FastAPI backend.
// No third-party dependencies. Env: PORT (default 3000), HOST (default 127.0.0.1), BACKEND_URL (default http://127.0.0.1:8000).
import http from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || "127.0.0.1";
const BACKEND = new URL(process.env.BACKEND_URL || "http://127.0.0.1:8000");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8" };
const SECURITY_HEADERS = {
  "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
  "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
};
const ASSETS = new Set([
  "index.html",
  "app.js",
  "core.js",
  "fmt.js",
  "ui.js",
  "beam.js",
  "chrome.js",
  "result.js",
  "design.js",
  "explore.js",
  "home.js",
  "chat.js",
  "kb.js",
  "system.js",
  "history.js",
  "scope.js",
  "fixture.js",
  "kbcharts.js",
  "theme-init.js",
  "styles.css",
  "theme.css",
]);

function proxy(req, res) {
  const up = http.request({
    host: BACKEND.hostname, port: BACKEND.port || 80, method: req.method, path: req.url,
    // overwrite (never append to) X-Forwarded-For so a client cannot spoof its address for rate limiting
    headers: { ...req.headers, host: BACKEND.host, "x-forwarded-for": req.socket.remoteAddress || "" },
  }, (r) => { res.writeHead(r.statusCode, r.headers); r.pipe(res); });
  up.setTimeout(300000, () => up.destroy(new Error("backend timeout")));
  up.on("error", (e) => { res.writeHead(502, { "Content-Type": "application/json" }); res.end(JSON.stringify({ detail: `backend unreachable: ${e.message}` })); });
  req.pipe(up);
}

async function serve(res, name) {
  if (!ASSETS.has(name)) { res.writeHead(404, { "Content-Type": "text/plain" }); return res.end("not found"); }
  try {
    const body = await readFile(path.join(ROOT, name));
    res.writeHead(200, { "Content-Type": TYPES[path.extname(name)], "Cache-Control": "no-cache", ...SECURITY_HEADERS });
    res.end(body);
  } catch { res.writeHead(500); res.end("read error"); }
}

http.createServer((req, res) => {
  const p = new URL(req.url, "http://x").pathname;
  if (p.startsWith("/api/")) return proxy(req, res);
  if (p === "/" || p === "/index.html") return serve(res, "index.html");
  if (p.startsWith("/static/")) return serve(res, p.slice("/static/".length));
  res.writeHead(404, { "Content-Type": "text/plain" }); res.end("not found");
}).listen(PORT, HOST, () => console.log(`SDC-V frontend on http://${HOST}:${PORT} -> backend ${BACKEND.origin}`));
