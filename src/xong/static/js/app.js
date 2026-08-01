/**
 * Xong check-off: strike + confetti-light + ding, then remove row (~800ms).
 * This interaction is the product.
 */
(function () {
  "use strict";

  const MUTE_KEY = "xong-muted";
  const COMPLETE_DELAY_MS = 820;

  function isMuted() {
    try {
      return localStorage.getItem(MUTE_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function setMuted(muted) {
    try {
      localStorage.setItem(MUTE_KEY, muted ? "1" : "0");
    } catch (_) {}
    const btn = document.getElementById("mute-toggle");
    if (btn) {
      btn.textContent = muted ? "🔇" : "🔊";
      btn.classList.toggle("is-muted", muted);
      btn.setAttribute("aria-label", muted ? "Bật âm" : "Tắt âm");
    }
  }

  let dingAudio = null;
  function getDing() {
    if (!dingAudio) {
      dingAudio = new Audio("/static/sounds/ding.wav");
      dingAudio.preload = "auto";
      dingAudio.volume = 0.55;
    }
    return dingAudio;
  }

  function playDing() {
    if (isMuted()) return;
    try {
      const a = getDing();
      a.currentTime = 0;
      const p = a.play();
      if (p && typeof p.catch === "function") p.catch(function () {});
    } catch (_) {}
  }

  /* Lightweight confetti burst near the checkbox */
  function burstConfetti(originEl) {
    const canvas = document.getElementById("confetti-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = window.innerWidth;
    const h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const rect = originEl.getBoundingClientRect();
    const ox = rect.left + rect.width / 2;
    const oy = rect.top + rect.height / 2;

    const colors = ["#3dcf8e", "#5b8def", "#f0c14b", "#e8ecf4", "#a78bfa"];
    const n = 28;
    const particles = [];
    for (let i = 0; i < n; i++) {
      const angle = (Math.PI * 2 * i) / n + (Math.random() - 0.5) * 0.4;
      const speed = 2.2 + Math.random() * 3.5;
      particles.push({
        x: ox,
        y: oy,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 1.5,
        g: 0.12 + Math.random() * 0.08,
        life: 1,
        decay: 0.018 + Math.random() * 0.012,
        size: 3 + Math.random() * 3.5,
        color: colors[i % colors.length],
        rot: Math.random() * Math.PI,
        vr: (Math.random() - 0.5) * 0.25,
      });
    }

    let raf = 0;
    function frame() {
      ctx.clearRect(0, 0, w, h);
      let alive = false;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        if (p.life <= 0) continue;
        alive = true;
        p.vy += p.g;
        p.x += p.vx;
        p.y += p.vy;
        p.vx *= 0.99;
        p.life -= p.decay;
        p.rot += p.vr;
        ctx.save();
        ctx.globalAlpha = Math.max(0, p.life);
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.65);
        ctx.restore();
      }
      if (alive) {
        raf = requestAnimationFrame(frame);
      } else {
        ctx.clearRect(0, 0, w, h);
      }
    }
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(frame);
  }

  function completeRow(row, btn) {
    if (row.classList.contains("is-completing")) return;
    row.classList.add("is-completing");
    playDing();
    burstConfetti(btn);

    const url = btn.getAttribute("data-complete-url");
    fetch(url, {
      method: "POST",
      headers: { "HX-Request": "true", Accept: "text/html" },
      credentials: "same-origin",
    }).catch(function () {});

    window.setTimeout(function () {
      row.classList.add("is-leaving");
      window.setTimeout(function () {
        row.remove();
      }, 380);
    }, COMPLETE_DELAY_MS);
  }

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".check-btn");
    if (!btn) return;
    e.preventDefault();
    const row = btn.closest(".task-row");
    if (!row) return;
    completeRow(row, btn);
  });

  document.addEventListener("DOMContentLoaded", function () {
    setMuted(isMuted());
    const muteBtn = document.getElementById("mute-toggle");
    if (muteBtn) {
      muteBtn.addEventListener("click", function () {
        setMuted(!isMuted());
      });
    }
    // Warm up audio on first gesture (browser autoplay policy)
    function warm() {
      try {
        getDing();
      } catch (_) {}
      document.removeEventListener("pointerdown", warm);
    }
    document.addEventListener("pointerdown", warm, { once: true });
  });
})();
