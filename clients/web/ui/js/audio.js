/* Xong — the ding. Synthesized with WebAudio, no audio files.
 * A soft mallet "ding": fundamental + two partials, fast attack, long decay,
 * plus a low body thock at the attack for warmth. Mute state persisted.
 */
(function () {
'use strict';

var MUTE_KEY = 'xong.muted';
var ctx = null;

function isMuted() {
  try { return localStorage.getItem(MUTE_KEY) === '1'; } catch (e) { return false; }
}

function setMuted(m) {
  try { localStorage.setItem(MUTE_KEY, m ? '1' : '0'); } catch (e) {}
}

function ensureCtx() {
  if (!ctx) {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  if (ctx.state === 'suspended') ctx.resume();
  return ctx;
}

function tone(c, dest, freq, type, start, peak, decay) {
  var osc = c.createOscillator();
  var gain = c.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(peak, start + 0.006);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + decay);
  osc.connect(gain);
  gain.connect(dest);
  osc.start(start);
  osc.stop(start + decay + 0.05);
}

function ding() {
  if (isMuted()) return;
  var c = ensureCtx();
  if (!c) return;
  var t = c.currentTime;
  var master = c.createGain();
  master.gain.value = 0.55;
  master.connect(c.destination);

  // E6 fundamental — the "ding" body.
  tone(c, master, 1318.51, 'sine', t, 0.50, 1.05);
  // Slightly detuned shimmer partial.
  tone(c, master, 1979.0, 'sine', t + 0.015, 0.16, 0.7);
  // High sparkle, a touch late — the "ping" tail.
  tone(c, master, 2637.02, 'sine', t + 0.09, 0.10, 0.5);
  // Low warm thock at attack.
  tone(c, master, 523.25, 'triangle', t, 0.18, 0.12);
}

// A softer, lower blip for un-doing — quiet, never scolding.
function undo() {
  if (isMuted()) return;
  var c = ensureCtx();
  if (!c) return;
  var t = c.currentTime;
  var master = c.createGain();
  master.gain.value = 0.3;
  master.connect(c.destination);
  tone(c, master, 659.25, 'sine', t, 0.25, 0.25);
}

window.XongAudio = { ding: ding, undo: undo, isMuted: isMuted, setMuted: setMuted };
})();
