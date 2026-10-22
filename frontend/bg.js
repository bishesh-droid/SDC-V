// Ambient background: a slowly drifting truss of joints and members with load pulses travelling along them.
// Decorative only. Pauses when the tab is hidden, draws a single still frame under prefers-reduced-motion.
(() => {
  const canvas = document.getElementById("bg");
  if (!canvas || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const LINK = 150, MOUSE = 170;
  let W = 0, H = 0, dpr = 1, nodes = [], pulses = [], raf = 0, last = 0, spawn = 0, frame = 0;
  let mouse = { x: -9999, y: -9999 };
  let col = { base: "34,211,238", pulse: "251,191,36", strength: 1 };

  function readColours() {
    const s = getComputedStyle(document.documentElement);
    col = { base: s.getPropertyValue("--bg-rgb").trim() || col.base, pulse: s.getPropertyValue("--bg-pulse-rgb").trim() || col.pulse,
      strength: parseFloat(s.getPropertyValue("--bg-strength")) || 1 };
  }
  function resize() {
    dpr = Math.min(devicePixelRatio || 1, 2);
    W = innerWidth; H = innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.max(26, Math.min(95, Math.round((W * H) / 20000)));
    nodes = Array.from({ length: n }, () => ({
      x: Math.random() * W, y: Math.random() * H, r: 1.3 + Math.random() * 1.6,
      vx: (Math.random() - 0.5) * 16, vy: (Math.random() - 0.5) * 16,
    }));
    pulses = [];
    readColours();
    if (reduce.matches) draw(0);
  }

  function draw(dt) {
    ctx.clearRect(0, 0, W, H);
    const k = col.strength;
    for (const p of nodes) {
      if (dt) {
        p.x += p.vx * dt; p.y += p.vy * dt;
        if (p.x < -20 || p.x > W + 20) p.vx *= -1;
        if (p.y < -20 || p.y > H + 20) p.vy *= -1;
      }
    }
    ctx.lineWidth = 1;
    const links = [];
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y, d = Math.hypot(dx, dy);
        if (d < LINK) {
          ctx.strokeStyle = `rgba(${col.base},${((1 - d / LINK) * 0.3 * k).toFixed(3)})`;
          ctx.beginPath(); ctx.moveTo(nodes[i].x, nodes[i].y); ctx.lineTo(nodes[j].x, nodes[j].y); ctx.stroke();
          links.push([i, j]);
        }
      }
    }
    // cursor "probe": members from the pointer to nearby joints
    for (const p of nodes) {
      const d = Math.hypot(p.x - mouse.x, p.y - mouse.y);
      if (d < MOUSE) {
        ctx.strokeStyle = `rgba(${col.pulse},${((1 - d / MOUSE) * 0.5 * k).toFixed(3)})`;
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke();
        if (dt) { p.x += (mouse.x - p.x) * 0.002; p.y += (mouse.y - p.y) * 0.002; }
      }
    }
    // joints drawn as small squares, like pinned connections
    ctx.fillStyle = `rgba(${col.base},${(0.6 * k).toFixed(3)})`;
    for (const p of nodes) ctx.fillRect(p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);

    // load pulses
    if (dt) {
      spawn -= dt;
      if (spawn <= 0 && links.length && pulses.length < 14) {
        const [a, b] = links[(Math.random() * links.length) | 0];
        pulses.push({ a, b, t: 0, speed: 0.5 + Math.random() * 0.6 });
        spawn = 0.35 + Math.random() * 0.5;
      }
    }
    pulses = pulses.filter((q) => (q.t += q.speed * dt) < 1);
    for (const q of pulses) {
      const A = nodes[q.a], B = nodes[q.b];
      if (Math.hypot(A.x - B.x, A.y - B.y) > LINK) { q.t = 1; continue; }
      const x = A.x + (B.x - A.x) * q.t, y = A.y + (B.y - A.y) * q.t, fade = Math.sin(Math.PI * q.t);
      const g = ctx.createRadialGradient(x, y, 0, x, y, 12);
      g.addColorStop(0, `rgba(${col.pulse},${(0.9 * fade * k).toFixed(3)})`); g.addColorStop(1, `rgba(${col.pulse},0)`);
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 12, 0, Math.PI * 2); ctx.fill();
    }
  }

  function loop(ts) {
    const dt = Math.min(0.05, (ts - last) / 1000 || 0); last = ts;
    if (++frame % 90 === 0) readColours();   // pick up theme changes
    draw(dt);
    raf = requestAnimationFrame(loop);
  }
  function start() { if (!raf && !reduce.matches && !document.hidden) { last = performance.now(); raf = requestAnimationFrame(loop); } }
  function stop() { cancelAnimationFrame(raf); raf = 0; }

  addEventListener("resize", () => { clearTimeout(resize.t); resize.t = setTimeout(resize, 150); });
  addEventListener("pointermove", (e) => { mouse = { x: e.clientX, y: e.clientY }; }, { passive: true });
  addEventListener("pointerleave", () => { mouse = { x: -9999, y: -9999 }; });
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
  reduce.addEventListener?.("change", () => { stop(); resize(); start(); });
  new MutationObserver(() => { readColours(); if (reduce.matches) draw(0); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  resize();
  start();
})();
