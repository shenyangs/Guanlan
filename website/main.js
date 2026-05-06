const canvas = document.querySelector("#research-field");
const ctx = canvas.getContext("2d");
const colors = ["#d44232", "#c8ff45", "#69d6ff", "#f5f2e9"];
let width = 0;
let height = 0;
let dpr = 1;
let points = [];
let pointer = { x: 0, y: 0, active: false };

function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  width = window.innerWidth;
  height = window.innerHeight;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const count = Math.max(70, Math.min(150, Math.floor((width * height) / 12000)));
  points = Array.from({ length: count }, (_, index) => ({
    x: Math.random() * width,
    y: Math.random() * height,
    seed: Math.random() * 1000,
    speed: 0.18 + Math.random() * 0.42,
    color: colors[index % colors.length],
    radius: 0.55 + Math.random() * 1.15,
  }));
}

function angleAt(x, y, time, seed) {
  const scale = 0.0022;
  return (
    Math.sin((x + seed * 17) * scale + time * 0.00018) +
    Math.cos((y - seed * 11) * scale - time * 0.00014)
  ) * Math.PI;
}

function drawGrid(time) {
  ctx.save();
  ctx.globalAlpha = 0.12;
  ctx.strokeStyle = "#f5f2e9";
  ctx.lineWidth = 1;
  const gap = width < 700 ? 76 : 96;
  for (let y = -gap; y < height + gap; y += gap) {
    ctx.beginPath();
    ctx.moveTo(0, y + Math.sin(time * 0.00016 + y) * 10);
    for (let x = 0; x <= width; x += 56) {
      ctx.lineTo(x, y + Math.sin(x * 0.006 + time * 0.00024 + y * 0.015) * 15);
    }
    ctx.stroke();
  }
  ctx.restore();
}

function animate(time = 0) {
  ctx.fillStyle = "rgba(5, 5, 5, 0.28)";
  ctx.fillRect(0, 0, width, height);
  drawGrid(time);

  for (const point of points) {
    const angle = angleAt(point.x, point.y, time, point.seed);
    let vx = Math.cos(angle) * point.speed;
    let vy = Math.sin(angle) * point.speed;
    if (pointer.active) {
      const dx = pointer.x - point.x;
      const dy = pointer.y - point.y;
      const distance = Math.hypot(dx, dy);
      if (distance < 190) {
        vx += (dx / Math.max(distance, 1)) * 0.16;
        vy += (dy / Math.max(distance, 1)) * 0.16;
      }
    }
    point.x += vx;
    point.y += vy;

    if (point.x < -20) point.x = width + 20;
    if (point.x > width + 20) point.x = -20;
    if (point.y < -20) point.y = height + 20;
    if (point.y > height + 20) point.y = -20;

    ctx.globalAlpha = 0.55;
    ctx.fillStyle = point.color;
    ctx.beginPath();
    ctx.arc(point.x, point.y, point.radius, 0, Math.PI * 2);
    ctx.fill();
  }

  requestAnimationFrame(animate);
}

window.addEventListener("resize", resize);
window.addEventListener("pointermove", (event) => {
  pointer = { x: event.clientX, y: event.clientY, active: true };
});
window.addEventListener("pointerleave", () => {
  pointer.active = false;
});

resize();
ctx.fillStyle = "#050505";
ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);
animate();

const screens = document.querySelectorAll(".screen");

if ("IntersectionObserver" in window) {
  const screenObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        entry.target.classList.toggle("is-visible", entry.isIntersecting);
      }
    },
    {
      root: null,
      threshold: 0.36,
      rootMargin: "-8% 0px -18% 0px",
    },
  );

  screens.forEach((screen, index) => {
    if (index === 0) screen.classList.add("is-visible");
    screenObserver.observe(screen);
  });
} else {
  screens.forEach((screen) => screen.classList.add("is-visible"));
}

document.querySelectorAll(".copy-button").forEach((button) => {
  button.addEventListener("click", async () => {
    const command = button.closest("li")?.querySelector("code")?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(command);
      button.classList.add("is-copied");
      button.textContent = "已复制";
      setTimeout(() => {
        button.classList.remove("is-copied");
        button.textContent = "复制";
      }, 1500);
    } catch {
      button.textContent = "复制失败";
    }
  });
});

function reportWebsiteVisit() {
  if (!/^https?:$/.test(window.location.protocol)) {
    return;
  }
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection || {};
  const payload = JSON.stringify({
    path: `${window.location.pathname}${window.location.search}`,
    referrer: document.referrer || "",
    language: navigator.language || "",
    languages: Array.isArray(navigator.languages) ? navigator.languages.join(",") : "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "",
    screen: `${window.screen?.width || 0}x${window.screen?.height || 0}`,
    viewport: `${window.innerWidth || 0}x${window.innerHeight || 0}`,
    device_pixel_ratio: String(window.devicePixelRatio || ""),
    network_effective_type: connection.effectiveType || "",
    network_downlink: connection.downlink ? String(connection.downlink) : "",
    network_rtt: connection.rtt ? String(connection.rtt) : "",
    network_save_data: connection.saveData ? "true" : "false",
  });
  const endpoint = "/guanlan-telemetry/v1/site-visits";
  if (navigator.sendBeacon) {
    navigator.sendBeacon(endpoint, new Blob([payload], { type: "application/json" }));
    return;
  }
  fetch(endpoint, {
    method: "POST",
    body: payload,
    headers: { "Content-Type": "application/json" },
    keepalive: true,
  }).catch(() => {});
}

reportWebsiteVisit();
