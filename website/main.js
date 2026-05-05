const canvas = document.querySelector("#flow-field");
const ctx = canvas.getContext("2d");
const colors = ["#d44232", "#c8ff45", "#70d7ff", "#f7efe3"];
let width = 0;
let height = 0;
let dpr = 1;
let particles = [];
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

  const count = Math.max(80, Math.min(180, Math.floor((width * height) / 9000)));
  particles = Array.from({ length: count }, (_, index) => ({
    x: Math.random() * width,
    y: Math.random() * height,
    seed: Math.random() * 1000,
    speed: 0.28 + Math.random() * 0.72,
    color: colors[index % colors.length],
    radius: 0.7 + Math.random() * 1.6,
  }));
}

function field(x, y, time, seed) {
  const scale = 0.0024;
  return (
    Math.sin((x + seed * 13) * scale + time * 0.00026) +
    Math.cos((y - seed * 7) * scale - time * 0.0002)
  );
}

function animate(time = 0) {
  ctx.fillStyle = "rgba(5, 5, 5, 0.24)";
  ctx.fillRect(0, 0, width, height);

  ctx.save();
  ctx.globalAlpha = 0.14;
  ctx.strokeStyle = "#f7efe3";
  ctx.lineWidth = 1;
  for (let y = 0; y < height; y += 86) {
    ctx.beginPath();
    ctx.moveTo(0, y + Math.sin(time * 0.00022 + y) * 14);
    for (let x = 0; x <= width; x += 64) {
      ctx.lineTo(x, y + Math.sin(x * 0.007 + time * 0.00032 + y * 0.018) * 20);
    }
    ctx.stroke();
  }
  ctx.restore();

  for (const particle of particles) {
    const angle = field(particle.x, particle.y, time, particle.seed) * Math.PI;
    let vx = Math.cos(angle) * particle.speed;
    let vy = Math.sin(angle) * particle.speed;
    if (pointer.active) {
      const dx = pointer.x - particle.x;
      const dy = pointer.y - particle.y;
      const distance = Math.hypot(dx, dy);
      if (distance < 210) {
        vx += (dx / Math.max(distance, 1)) * 0.28;
        vy += (dy / Math.max(distance, 1)) * 0.28;
      }
    }
    particle.x += vx;
    particle.y += vy;

    if (particle.x < -20) particle.x = width + 20;
    if (particle.x > width + 20) particle.x = -20;
    if (particle.y < -20) particle.y = height + 20;
    if (particle.y > height + 20) particle.y = -20;

    ctx.globalAlpha = 0.64;
    ctx.fillStyle = particle.color;
    ctx.beginPath();
    ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
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

document.querySelectorAll(".copy-button").forEach((button) => {
  button.addEventListener("click", async () => {
    const command = button.closest("article")?.querySelector("code")?.textContent ?? "";
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
