/* Xong — confetti-light particle burst for check-off.
 * Tiny fixed-position spans animated with WAAPI; no canvas, no libraries.
 * Calm palette, short life, respectful of prefers-reduced-motion.
 */
(function () {
'use strict';

var COLORS = ['#c2501f', '#e8854a', '#a8441a', '#f0a35e', '#d9a05b', '#8a4b1f'];

function reducedMotion() {
  return window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function burst(x, y) {
  if (reducedMotion()) return;

  // Expanding ring from the checkbox.
  var ring = document.createElement('span');
  ring.className = 'xong-ring';
  ring.style.left = x + 'px';
  ring.style.top = y + 'px';
  document.body.appendChild(ring);
  ring.animate(
    [
      { transform: 'translate(-50%, -50%) scale(0.3)', opacity: 0.9 },
      { transform: 'translate(-50%, -50%) scale(2.2)', opacity: 0 }
    ],
    { duration: 420, easing: 'cubic-bezier(.2,.7,.3,1)' }
  ).onfinish = function () { ring.remove(); };

  // Particle burst — radial, slight upward bias, then drift down.
  var n = 16;
  for (var i = 0; i < n; i++) {
    var p = document.createElement('span');
    p.className = 'xong-particle';
    var size = 4 + Math.random() * 5;
    p.style.width = size + 'px';
    p.style.height = size + 'px';
    p.style.left = x + 'px';
    p.style.top = y + 'px';
    p.style.background = COLORS[(Math.random() * COLORS.length) | 0];
    if (Math.random() < 0.5) p.style.borderRadius = '50%';
    else p.style.borderRadius = '1.5px';
    document.body.appendChild(p);

    var angle = (Math.PI * 2 * i) / n + (Math.random() - 0.5) * 0.6;
    var dist = 34 + Math.random() * 52;
    var dx = Math.cos(angle) * dist;
    var dy = Math.sin(angle) * dist * 0.9 - 18; // bias upward
    var fall = 26 + Math.random() * 30;         // then gravity wins
    var rot = (Math.random() - 0.5) * 340;
    var dur = 620 + Math.random() * 260;

    p.animate(
      [
        { transform: 'translate(-50%,-50%) translate(0,0) rotate(0deg) scale(1)', opacity: 1, offset: 0 },
        { transform: 'translate(-50%,-50%) translate(' + dx + 'px,' + dy + 'px) rotate(' + rot * 0.6 + 'deg) scale(1)', opacity: 1, offset: 0.55 },
        { transform: 'translate(-50%,-50%) translate(' + dx * 1.15 + 'px,' + (dy + fall) + 'px) rotate(' + rot + 'deg) scale(0.6)', opacity: 0, offset: 1 }
      ],
      { duration: dur, easing: 'cubic-bezier(.16,.84,.35,1)' }
    ).onfinish = (function (el) {
      return function () { el.remove(); };
    })(p);
  }
}

window.XongConfetti = { burst: burst };
})();
