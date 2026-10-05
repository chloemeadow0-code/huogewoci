/* 入场画卷：开卷落墨、落名号、十二宗环盘、凭证登入。样式见 gate.css。 */

const SECTS = [
  { id: "qingxiao", name: "青霄剑宗", glyph: "剑", fac: "正道", desc: "剑修与实战。一剑既出，不问归途。" },
  { id: "xuanheng", name: "玄衡阵门", glyph: "阵", fac: "正道", desc: "阵法与机关。天地为盘，万象为子。" },
  { id: "danxia", name: "丹霞谷", glyph: "丹", fac: "正道", desc: "丹药与医修。一炉烟火，济世救人。" },
  { id: "fuyao", name: "伏妖门", glyph: "兽", fac: "正道", desc: "御兽与荒野。与兽同行，守山护林。" },
  { id: "taixu", name: "太虚观", glyph: "雷", fac: "正道", desc: "雷法与符箓。引九天之霆，正人间不平。" },
  { id: "hehuan", name: "合欢宗", glyph: "欢", fac: "魔道", desc: "魅道与汲取。花开两朵，各表一枝。" },
  { id: "youming", name: "幽冥殿", glyph: "冥", fac: "魔道", desc: "煞道与借煞。月照幽冥，借影而行。" },
  { id: "fentian", name: "焚天谷", glyph: "炎", fac: "中立", desc: "炎道与点燃。心火不熄，谁都不服。" },
  { id: "tiangong", name: "天工阁", glyph: "工", fac: "中立", desc: "锻造与器修。万器起于一锤。" },
  { id: "canglang", name: "沧浪水榭", glyph: "水", fac: "正道", desc: "水道与治疗。上善若水，泽被苍生。" },
  { id: "wanxiang", name: "万象楼", glyph: "商", fac: "中立", desc: "商道与消息。万象皆可入账。" },
  { id: "xingluo", name: "星罗卫", glyph: "星", fac: "正道", desc: "缉拿与悬赏。天网星罗，疏而不漏。" },
];

function tone(f0, f1, dur, type, gain, when = 0) {
  try {
    if (!tone.ctx) tone.ctx = new (window.AudioContext || window.webkitAudioContext)();
    const c = tone.ctx;
    if (c.state === "suspended") c.resume();
    const t = c.currentTime + when;
    const o = c.createOscillator(), g = c.createGain();
    o.type = type;
    o.frequency.setValueAtTime(f0, t);
    if (f1) o.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t + dur);
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(c.destination);
    o.start(t); o.stop(t + dur + 0.05);
  } catch (e) { /* 无声环境静默降级 */ }
}
function splashNoise(dur, gain, when = 0) {
  try {
    if (!tone.ctx) return;
    const c = tone.ctx, t = c.currentTime + when;
    const n = Math.floor(c.sampleRate * dur);
    const buf = c.createBuffer(1, n, c.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const src = c.createBufferSource(); src.buffer = buf;
    const bp = c.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 2600; bp.Q.value = .8;
    const g = c.createGain(); g.gain.value = gain;
    src.connect(bp).connect(g).connect(c.destination);
    src.start(t);
  } catch (e) {}
}
const PENTA = [261.6, 293.7, 329.6, 392, 440, 523.3, 587.3, 659.3];
const sndSplash = (when = 0) => { tone(760, 150, 0.32, "sine", 0.12, when); tone(1520, 620, 0.14, "sine", 0.04, when); splashNoise(0.14, 0.04, when); };
const sndPluck = (i, when = 0) => { const f = PENTA[((i % PENTA.length) + PENTA.length) % PENTA.length]; tone(f, f * 0.995, 0.55, "triangle", 0.045, when); tone(f * 2, 0, 0.18, "sine", 0.018, when); };
const sndStamp = (when = 0) => { tone(150, 52, 0.26, "sine", 0.2, when); splashNoise(0.07, 0.05, when); };
const sndTap = () => tone(1180, 640, 0.09, "sine", 0.025);

const HERO = "霁色入山海，心安即仙途。";
const CORE_DEFAULT =
  "移印入环，或点下方独行。<br>悬停任一宗门，此处自会介绍。";

export function mountGate({ register, loginByKey }) {
  const gate = document.getElementById("gate");
  const scenes = {};
  for (const id of ["gate-load", "gate-title", "gate-name", "gate-sect", "gate-key"]) {
    scenes[id] = document.getElementById(id);
  }
  let current = "gate-load";
  function go(id) {
    if (!scenes[id] || id === current) return;
    scenes[current].classList.remove("on");
    scenes[id].classList.add("on");
    current = id;
  }

  /* 点击反馈：墨滴洇纸 + 水面涟漪 */
  const inkLayer = document.getElementById("gate-ink");
  gate.addEventListener("pointerdown", e => {
    const drop = document.createElement("div");
    drop.className = "ink-drop";
    drop.style.left = e.clientX + "px";
    drop.style.top = e.clientY + "px";
    drop.innerHTML =
      '<i class="halo"></i>' +
      '<i class="blot" style="animation-duration:' + (1.15 + Math.random() * 0.25).toFixed(2) + 's"></i>' +
      '<i class="ripple"></i><i class="ripple"></i><i class="ripple"></i><i class="ripple"></i>';
    drop.querySelector(".blot").style.rotate = (Math.random() * 60 - 30).toFixed(1) + "deg";
    if (e.target.closest("button")) drop.querySelectorAll(".ripple").forEach(r => { r.style.borderWidth = "1.6px"; });
    inkLayer.appendChild(drop);
    setTimeout(() => drop.remove(), 1800);
    sndTap();
  });

  /* 标题逐字浮现（五声音阶随行） */
  const heroEl = document.getElementById("gate-hero-title");
  [...HERO].forEach((ch, i) => {
    const s = document.createElement("span");
    s.textContent = ch;
    const delay = 0.7 + i * 0.13;
    s.style.animationDelay = delay + "s";
    heroEl.appendChild(s);
    if (ch.trim()) sndPluck(i, delay);
  });

  /* 开卷：轻触纸面，墨滴落水 */
  const load = scenes["gate-load"];
  load.addEventListener("pointerdown", () => {
    if (load.classList.contains("falling")) return;
    load.classList.add("falling");
    sndSplash(0.5);
    [...load.querySelectorAll(".gate-load-word span")].forEach((s, i) => {
      s.style.animationDelay = (0.9 + i * 0.22) + "s";
      sndPluck(i + 2, 0.9 + i * 0.22);
    });
    setTimeout(() => {
      load.classList.add("done");
      setTimeout(() => go("gate-title"), 1050);
    }, 2600);
  });

  /* 入世修仙 → 落名号 */
  document.getElementById("gate-enter").addEventListener("click", () => {
    sndStamp();
    setTimeout(() => go("gate-name"), 380);
  });

  /* 已有凭证 → 凭证场景 */
  document.getElementById("gate-to-key").addEventListener("click", () => go("gate-key"));
  document.getElementById("gate-back-title").addEventListener("click", () => go("gate-title"));
  const keyInput = document.getElementById("gate-key-input");
  const keyError = document.getElementById("gate-key-error");
  async function submitKey() {
    const key = keyInput.value.trim();
    if (!key) { keyError.textContent = "凭证为空，去岛上落个名号也一样。"; return; }
    keyError.textContent = "";
    try {
      await loginByKey(key);
    } catch (error) {
      keyError.textContent = error.message;
    }
  }
  document.getElementById("gate-login").addEventListener("click", submitKey);
  keyInput.addEventListener("keydown", e => { if (e.key === "Enter") submitKey(); });

  /* 落笔为凭 → 环盘 */
  const daoInput = document.getElementById("gate-dao-input");
  const daoError = document.getElementById("gate-dao-error");
  document.getElementById("gate-dao-btn").addEventListener("click", submitDao);
  daoInput.addEventListener("keydown", e => { if (e.key === "Enter") submitDao(); });
  function submitDao() {
    const name = daoInput.value.trim();
    if (name.length < 2) {
      daoError.textContent = "道号至少两字，才好落款。";
      daoInput.focus();
      return;
    }
    daoError.textContent = "";
    document.getElementById("gate-dao-show").textContent = name;
    go("gate-sect");
    popWheel();
  }

  /* 十二宗环盘 */
  const FAC_COLOR = { "正道": "#191c1b", "魔道": "#a33831", "中立": "#a98a54" };
  const wheel = document.getElementById("gate-wheel");
  const coreName = document.getElementById("gate-core-name");
  const coreDesc = document.getElementById("gate-core-desc");
  let wheelTimers = [];

  SECTS.forEach((s, i) => {
    const d = document.createElement("button");
    d.className = "gate-disc";
    d.type = "button";
    d.style.setProperty("--a", (i * 30 - 90) + "deg");
    d.style.setProperty("--r", "min(24vmin, 215px)");
    d.style.color = FAC_COLOR[s.fac];
    d.innerHTML =
      '<span class="gate-disc-inner">' + s.glyph + '<span class="fac">' + s.fac + "</span></span>" +
      '<span class="mini-stamp">入</span>';
    d.addEventListener("click", () => chooseSect(d, s));
    d.addEventListener("mouseenter", () => {
      coreName.textContent = s.name.split("").join(" ");
      coreDesc.innerHTML = "<em>" + s.fac + "</em> · " + s.desc;
    });
    d.addEventListener("mouseleave", () => {
      coreName.textContent = "灵 汐 岛";
      coreDesc.innerHTML = CORE_DEFAULT;
    });
    wheel.appendChild(d);
  });

  /* 小屏降级网格 */
  const fb = document.getElementById("gate-wheel-fallback");
  SECTS.forEach(s => {
    const d = document.createElement("button");
    d.className = "gate-disc";
    d.type = "button";
    d.innerHTML =
      '<span class="gate-disc-inner">' + s.glyph + '<span class="fac">' + s.name + "</span></span>" +
      '<span class="mini-stamp">入</span>';
    d.addEventListener("click", () => enterWorld(s.id, s.name));
    fb.appendChild(d);
  });

  function popWheel() {
    wheelTimers.forEach(clearTimeout); wheelTimers = [];
    [...wheel.querySelectorAll(".gate-disc")].forEach(d => d.classList.remove("on", "chosen", "fading"));
    const discs = [...wheel.querySelectorAll(".gate-disc")];
    discs.forEach((d, i) => {
      wheelTimers.push(setTimeout(() => { d.classList.add("on"); sndPluck(i + 1); }, 350 + i * 120));
    });
    wheelTimers.push(setTimeout(sndStamp, 300));
  }

  async function chooseSect(disc, s) {
    if (disc.classList.contains("chosen")) return;
    sndStamp(0.05);
    wheelTimers.forEach(clearTimeout);
    [...wheel.querySelectorAll(".gate-disc")].forEach(d => {
      if (d === disc) { d.classList.add("chosen"); d.classList.remove("fading"); }
      else d.classList.add("fading");
    });
    document.getElementById("gate-rogue").style.opacity = "0";
    await enterWorld(s.id, s.name);
  }

  document.getElementById("gate-rogue").addEventListener("click", async () => {
    sndStamp(0.05);
    await enterWorld("rogue", "散修");
  });

  async function enterWorld(sectId, sectName) {
    try {
      await register(daoInput.value.trim(), sectId, sectName);
    } catch (error) {
      document.getElementById("gate-sect-error").textContent = "入岛未成：" + error.message;
      document.getElementById("gate-rogue").style.opacity = "";
      [...wheel.querySelectorAll(".gate-disc")].forEach(d => d.classList.remove("chosen", "fading"));
      popWheel();
    }
  }

  /* 登出后从标题页重新来过 */
  gate.__showTitle = () => {
    for (const id in scenes) scenes[id].classList.remove("on", "done", "falling");
    current = "gate-load";
    daoInput.value = "";
    keyInput.value = "";
    daoError.textContent = ""; keyError.textContent = "";
    document.getElementById("gate-sect-error").textContent = "";
    document.getElementById("gate-rogue").style.opacity = "";
    scenes["gate-title"].classList.add("on");
    current = "gate-title";
  };
}

export function gateShow() {
  const gate = document.getElementById("gate");
  gate.hidden = false;
  if (gate.__showTitle) gate.__showTitle();
}

export function gateHide() {
  document.getElementById("gate").hidden = true;
}
