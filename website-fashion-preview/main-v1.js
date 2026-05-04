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

  const count = Math.max(90, Math.min(220, Math.floor((width * height) / 7800)));
  particles = Array.from({ length: count }, (_, index) => ({
    x: Math.random() * width,
    y: Math.random() * height,
    seed: Math.random() * 1000,
    speed: 0.34 + Math.random() * 0.9,
    color: colors[index % colors.length],
    radius: 0.8 + Math.random() * 1.8,
  }));
}

function field(x, y, time, seed) {
  const scale = 0.0026;
  return (
    Math.sin((x + seed * 13) * scale + time * 0.00032) +
    Math.cos((y - seed * 7) * scale - time * 0.00024)
  );
}

function draw(time = 0) {
  ctx.fillStyle = "rgba(5, 5, 5, 0.18)";
  ctx.fillRect(0, 0, width, height);

  ctx.save();
  ctx.globalAlpha = 0.18;
  ctx.strokeStyle = "#f7efe3";
  ctx.lineWidth = 1;
  for (let y = 0; y < height; y += 74) {
    ctx.beginPath();
    ctx.moveTo(0, y + Math.sin(time * 0.0003 + y) * 18);
    for (let x = 0; x <= width; x += 56) {
      ctx.lineTo(x, y + Math.sin(x * 0.008 + time * 0.0004 + y * 0.02) * 26);
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
      if (distance < 220) {
        vx += (dx / Math.max(distance, 1)) * 0.35;
        vy += (dy / Math.max(distance, 1)) * 0.35;
      }
    }

    particle.x += vx;
    particle.y += vy;

    if (particle.x < -20) particle.x = width + 20;
    if (particle.x > width + 20) particle.x = -20;
    if (particle.y < -20) particle.y = height + 20;
    if (particle.y > height + 20) particle.y = -20;

    ctx.globalAlpha = 0.72;
    ctx.fillStyle = particle.color;
    ctx.beginPath();
    ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
    ctx.fill();
  }

  requestAnimationFrame(draw);
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
draw();

const commandOutput = document.querySelector("#command-output");
const copyButton = document.querySelector("#copy-command");

if (copyButton && commandOutput) {
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(commandOutput.textContent.trim());
      copyButton.textContent = "Copied";
      setTimeout(() => {
        copyButton.textContent = "Copy";
      }, 1400);
    } catch {
      copyButton.textContent = "Failed";
    }
  });
}
