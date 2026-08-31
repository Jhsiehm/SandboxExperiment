/* Pixel workshop: shelves for search, enchanting table + workbench for maths. */
(function () {
  const GLYPHS = "ᔑʖᓵ↸ᒷ⎓⊣⍑╎⋮ꖌꖎᒲリ𝙹¡ᑑ∷ᓭℸ⚍⍊∴||⨅*".split("");
  const CAPTION = {
    idle: "Librarian at the desk. Click the stone floor — or Run practice — to send them to the 2012 shelves.",
    search: "Pulling volumes off the 2012 shelves. Glyphs streaming to the table.",
    maths: "Workbench + enchanting table. Hover a slot to translate the Standard Galactic.",
    done: "Enchantment complete. +XP. Scores are in the ledger above.",
    error: "The table fizzled. Check the run log.",
  };

  const glyphs = [];
  const motes = [];
  const sparkles = [];
  const orbs = [];
  let pose = "idle";
  let canvas;
  let ctx;
  let w = 0;
  let h = 0;
  let tick = 0;
  let reduced = false;

  function root() {
    return document.getElementById("enchant");
  }

  function caption() {
    return document.getElementById("enchant-caption");
  }

  function spawnGlyph(kind) {
    const left = Math.random() < 0.5;
    const g = {
      ch: GLYPHS[(Math.random() * GLYPHS.length) | 0],
      kind,
      x: left ? w * (0.04 + Math.random() * 0.16) : w * (0.78 + Math.random() * 0.16),
      y: h * (0.1 + Math.random() * 0.32),
      tx: w * 0.5,
      ty: h * 0.72,
      life: 0,
      max: 55 + Math.random() * 45,
      size: 12 + Math.random() * 12,
      hue: 270 + Math.random() * 40,
      angle: Math.random() * Math.PI * 2,
      radius: Math.min(w, h) * (0.12 + Math.random() * 0.18),
      spin: (Math.random() < 0.5 ? -1 : 1) * (0.025 + Math.random() * 0.04),
    };
    glyphs.push(g);
  }

  function spawnMote() {
    motes.push({
      x: w * 0.5 + (Math.random() * 50 - 25),
      y: h * 0.72,
      vx: Math.random() * 1.4 - 0.7,
      vy: -0.5 - Math.random() * 1.6,
      life: 0,
      max: 36 + Math.random() * 28,
      r: 1 + Math.random() * 2.4,
    });
  }

  function spawnSpark() {
    sparkles.push({
      x: w * (0.22 + Math.random() * 0.56),
      y: h * (0.18 + Math.random() * 0.5),
      life: 0,
      max: 18 + Math.random() * 16,
      s: 2 + Math.random() * 3,
    });
  }

  function spawnOrb() {
    orbs.push({
      x: w * 0.5 + (Math.random() * 80 - 40),
      y: h * 0.7,
      vy: -1.2 - Math.random() * 1.1,
      life: 0,
      max: 50 + Math.random() * 20,
      r: 3 + Math.random() * 3,
    });
  }

  function setPose(next) {
    if (!root()) return;
    pose = next || "idle";
    root().dataset.pose = pose;
    const cap = caption();
    if (cap) cap.textContent = CAPTION[pose] || CAPTION.idle;
    if (pose === "maths") {
      for (let i = 0; i < 10; i++) spawnGlyph("orbit");
    }
    if (pose === "done") {
      for (let i = 0; i < 8; i++) spawnOrb();
    }
  }

  function resize() {
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    w = canvas.width = Math.max(320, Math.floor(rect.width));
    h = canvas.height = Math.max(180, Math.floor(rect.height));
  }

  function drawPlus(x, y, s, alpha) {
    ctx.fillStyle = `rgba(233, 213, 255, ${alpha})`;
    ctx.fillRect(x - s, y - 1, s * 2, 2);
    ctx.fillRect(x - 1, y - s, 2, s * 2);
  }

  function draw() {
    if (!ctx) return;
    tick += 1;
    ctx.clearRect(0, 0, w, h);

    const streamRate = pose === "search" ? 0.28 : pose === "maths" ? 0.42 : pose === "done" ? 0.12 : 0.03;
    if (!reduced && Math.random() < streamRate) spawnGlyph(pose === "maths" ? "orbit" : "stream");
    if (!reduced && (pose === "maths" || pose === "done") && Math.random() < 0.45) spawnMote();
    if (!reduced && pose !== "idle" && Math.random() < 0.2) spawnSpark();
    if (!reduced && pose === "done" && Math.random() < 0.08) spawnOrb();

    if (glyphs.length > 90) glyphs.splice(0, glyphs.length - 90);
    if (pose === "maths") {
      const pulse = 0.28 + 0.22 * Math.sin(tick / 7);
      const rad = Math.min(w, h) * 0.22;
      const cy = h * 0.72;
      const grd = ctx.createRadialGradient(w / 2, cy, 8, w / 2, cy, rad);
      grd.addColorStop(0, `rgba(233, 213, 255, ${pulse})`);
      grd.addColorStop(0.35, `rgba(168, 85, 247, ${pulse * 0.45})`);
      grd.addColorStop(1, "rgba(88, 28, 135, 0)");
      ctx.fillStyle = grd;
      ctx.fillRect(w / 2 - rad, cy - rad, rad * 2, rad * 2);
    }

    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let i = glyphs.length - 1; i >= 0; i--) {
      const g = glyphs[i];
      g.life += 1;
      const t = g.life / g.max;
      if (g.kind === "orbit") {
        g.angle += g.spin;
        g.radius *= 0.992;
        g.x = w * 0.5 + Math.cos(g.angle) * g.radius;
        g.y = h * 0.7 + Math.sin(g.angle) * g.radius * 0.38;
      } else {
        g.x += (g.tx - g.x) * 0.05;
        g.y += (g.ty - g.y) * 0.05;
      }
      const alpha = t < 0.12 ? t / 0.12 : 1 - (t - 0.12) / 0.88;
      ctx.font = `700 ${g.size}px "IBM Plex Mono", monospace`;
      ctx.fillStyle = `hsla(${g.hue}, 92%, 74%, ${Math.max(0, alpha)})`;
      ctx.shadowColor = `hsla(${g.hue}, 100%, 70%, 0.95)`;
      ctx.shadowBlur = 10;
      ctx.fillText(g.ch, g.x, g.y);
      if (g.life > g.max) glyphs.splice(i, 1);
    }
    ctx.restore();

    for (let i = motes.length - 1; i >= 0; i--) {
      const m = motes[i];
      m.life += 1;
      m.x += m.vx;
      m.y += m.vy;
      const a = 1 - m.life / m.max;
      ctx.fillStyle = `rgba(196, 181, 253, ${a})`;
      ctx.fillRect(m.x, m.y, m.r, m.r);
      if (m.life > m.max) motes.splice(i, 1);
    }

    for (let i = sparkles.length - 1; i >= 0; i--) {
      const s = sparkles[i];
      s.life += 1;
      drawPlus(s.x, s.y, s.s, 1 - s.life / s.max);
      if (s.life > s.max) sparkles.splice(i, 1);
    }

    for (let i = orbs.length - 1; i >= 0; i--) {
      const o = orbs[i];
      o.life += 1;
      o.y += o.vy;
      const a = 1 - o.life / o.max;
      ctx.fillStyle = `rgba(74, 222, 128, ${a})`;
      ctx.fillRect(o.x, o.y, o.r, o.r);
      ctx.fillStyle = `rgba(187, 247, 208, ${a})`;
      ctx.fillRect(o.x + 1, o.y + 1, Math.max(1, o.r - 2), Math.max(1, o.r - 2));
      if (o.life > o.max) orbs.splice(i, 1);
    }

    if (!reduced) requestAnimationFrame(draw);
  }

  function boot() {
    reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    canvas = document.getElementById("enchant-fx");
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    resize();
    window.addEventListener("resize", resize);
    setPose("idle");
    const qPose = new URLSearchParams(location.search).get("pose");
    if (qPose && CAPTION[qPose]) setPose(qPose);
    const stage = root();
    stage.addEventListener("click", (ev) => {
      if (ev.target.closest(".enchant-menu") || ev.target.closest(".hud")) return;
      const cycle = ["search", "maths", "done", "idle"];
      const i = Math.max(0, cycle.indexOf(pose));
      setPose(cycle[(i + 1) % cycle.length]);
    });
    if (reduced) {
      spawnGlyph("stream");
      spawnGlyph("orbit");
      draw();
      return;
    }
    draw();
  }

  window.Enchant = { setPose, boot };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
