/** 彩蛋：全屏爆炸特效（闪光 + 冲击波 + 粒子 + 屏幕震动）。
 *  纯 DOM/Web Animations 实现，无依赖，任意页面可调用。 */

const EGG_KEYWORD = "泠雨";

/** 输入是否命中彩蛋 */
export function hitsEasterEgg(text: string): boolean {
  return text.trim() === EGG_KEYWORD || text.trim().includes(`「${EGG_KEYWORD}」`);
}

const PALETTE = ["#38bdf8", "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#f87171", "#e2e8f0"];

export function fireScreenExplosion(): void {
  if (typeof window === "undefined") return;
  const W = window.innerWidth;
  const H = window.innerHeight;
  const cx = W / 2;
  const cy = H / 2;

  const root = document.createElement("div");
  root.style.cssText = "position:fixed;inset:0;z-index:9999;pointer-events:none;overflow:hidden";
  document.body.appendChild(root);

  // 1) 白闪
  const flash = document.createElement("div");
  flash.style.cssText = `position:absolute;inset:0;background:radial-gradient(circle at ${cx}px ${cy}px, rgba(255,255,255,0.95), rgba(255,200,120,0.55) 30%, transparent 62%)`;
  root.appendChild(flash);
  flash.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 420, easing: "ease-out", fill: "forwards" });

  // 2) 冲击波双环
  const rings: Array<[number, number, string]> = [
    [0, 90, "rgba(251,191,36,0.9)"],
    [140, 40, "rgba(56,189,248,0.8)"],
  ];
  for (const [delay, size, color] of rings) {
    const ring = document.createElement("div");
    ring.style.cssText = `position:absolute;left:${cx}px;top:${cy}px;width:${size}px;height:${size}px;margin:${-size / 2}px;border-radius:9999px;border:3px solid ${color}`;
    root.appendChild(ring);
    ring.animate(
      [
        { transform: "scale(0.2)", opacity: 1 },
        { transform: `scale(${Math.max(W, H) / size})`, opacity: 0 },
      ],
      { duration: 900, delay, easing: "cubic-bezier(0.16, 1, 0.3, 1)", fill: "forwards" }
    );
  }

  // 3) 粒子乱飞（随机角度/速度/旋转 + 拖尾感的先快后慢）
  for (let i = 0; i < 90; i++) {
    const p = document.createElement("div");
    const s = 4 + Math.random() * 10;
    const color = PALETTE[i % PALETTE.length];
    const round = Math.random() > 0.4;
    p.style.cssText = `position:absolute;left:${cx}px;top:${cy}px;width:${s}px;height:${s}px;${
      round ? `border-radius:9999px;background:${color}` : `background:transparent;border:2px solid ${color}`
    };box-shadow:0 0 ${6 + s}px ${color}`;
    root.appendChild(p);
    const angle = Math.random() * Math.PI * 2;
    const speed = 220 + Math.random() * 720;
    const dx = Math.cos(angle) * speed;
    const dy = Math.sin(angle) * speed * 0.85;
    p.animate(
      [
        { transform: "translate(-50%,-50%) rotate(0deg)", opacity: 1 },
        {
          transform: `translate(calc(-50% + ${dx}px), calc(-50% + ${dy + 240}px)) rotate(${(Math.random() - 0.5) * 1440}deg)`,
          opacity: 0,
        },
      ],
      { duration: 900 + Math.random() * 900, easing: "cubic-bezier(0.12, 0.8, 0.3, 1)", fill: "forwards" }
    );
  }

  // 4) 中心 💥 + 彩蛋字幕
  const boom = document.createElement("div");
  boom.textContent = "💥";
  boom.style.cssText = `position:absolute;left:${cx}px;top:${cy}px;font-size:96px;transform:translate(-50%,-50%)`;
  root.appendChild(boom);
  boom.animate(
    [
      { transform: "translate(-50%,-50%) scale(0.3)", opacity: 0 },
      { transform: "translate(-50%,-50%) scale(1.25)", opacity: 1, offset: 0.25 },
      { transform: "translate(-50%,-50%) scale(1)", opacity: 1, offset: 0.7 },
      { transform: "translate(-50%,-50%) scale(1)", opacity: 0 },
    ],
    { duration: 1800, easing: "ease-out", fill: "forwards" }
  );
  const caption = document.createElement("div");
  caption.textContent = "泠雨引爆了整个屏幕！";
  caption.style.cssText = `position:absolute;left:${cx}px;top:${cy + 90}px;transform:translateX(-50%);font-weight:700;font-size:22px;color:#fde68a;text-shadow:0 2px 18px rgba(251,191,36,0.8);letter-spacing:2px;white-space:nowrap`;
  root.appendChild(caption);
  caption.animate(
    [
      { opacity: 0, transform: "translateX(-50%) translateY(14px)" },
      { opacity: 1, transform: "translateX(-50%) translateY(0)", offset: 0.3 },
      { opacity: 1, transform: "translateX(-50%) translateY(0)", offset: 0.75 },
      { opacity: 0, transform: "translateX(-50%) translateY(-10px)" },
    ],
    { duration: 2000, easing: "ease-out", fill: "forwards" }
  );

  // 5) 屏幕震动（只晃主要内容区，避免 fixed 布局抖裂）
  const shakeTarget = document.querySelector("main") || document.body;
  shakeTarget.animate(
    [
      { transform: "translate(0,0) rotate(0)" },
      { transform: "translate(-16px,9px) rotate(-0.7deg)" },
      { transform: "translate(13px,-7px) rotate(0.6deg)" },
      { transform: "translate(-9px,5px) rotate(-0.35deg)" },
      { transform: "translate(6px,-3px) rotate(0.2deg)" },
      { transform: "translate(0,0) rotate(0)" },
    ],
    { duration: 620, easing: "ease-in-out" }
  );

  setTimeout(() => root.remove(), 2700);
}
