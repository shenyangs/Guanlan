const canvas = document.querySelector("#signal-canvas");
const ctx = canvas.getContext("2d");

const palette = ["#32d5ff", "#b7ff4a", "#ffc857", "#ff4d8d", "#a77dff"];
let width = 0;
let height = 0;
let dpr = 1;
let pointer = { x: 0, y: 0, active: false };
let nodes = [];

function resize() {
  dpr = Math.min(window.devicePixelRatio || 1, 2);
  width = window.innerWidth;
  height = window.innerHeight;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const count = Math.max(38, Math.min(92, Math.floor((width * height) / 19000)));
  nodes = Array.from({ length: count }, (_, index) => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.28,
    vy: (Math.random() - 0.5) * 0.28,
    radius: Math.random() * 1.6 + 1,
    color: palette[index % palette.length],
  }));
}

function drawGrid(time) {
  ctx.save();
  ctx.globalAlpha = 0.32;
  ctx.strokeStyle = "rgba(214, 252, 255, 0.08)";
  ctx.lineWidth = 1;
  const gap = 64;
  const offset = (time * 0.018) % gap;

  for (let x = -gap + offset; x < width + gap; x += gap) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x + height * 0.18, height);
    ctx.stroke();
  }

  for (let y = -gap + offset; y < height + gap; y += gap) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y + width * 0.08);
    ctx.stroke();
  }
  ctx.restore();
}

function drawRadar(time) {
  const cx = width * 0.68;
  const cy = height * 0.46;
  const maxRadius = Math.min(width, height) * 0.34;
  const angle = time * 0.00036;

  ctx.save();
  ctx.translate(cx, cy);
  ctx.strokeStyle = "rgba(50, 213, 255, 0.18)";
  ctx.lineWidth = 1;

  for (let i = 1; i <= 4; i += 1) {
    ctx.beginPath();
    ctx.arc(0, 0, (maxRadius / 4) * i, 0, Math.PI * 2);
    ctx.stroke();
  }

  for (let i = 0; i < 8; i += 1) {
    const a = (Math.PI * 2 * i) / 8;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(Math.cos(a) * maxRadius, Math.sin(a) * maxRadius);
    ctx.stroke();
  }

  const sweep = ctx.createRadialGradient(0, 0, 0, 0, 0, maxRadius);
  sweep.addColorStop(0, "rgba(183, 255, 74, 0.28)");
  sweep.addColorStop(1, "rgba(50, 213, 255, 0)");
  ctx.rotate(angle);
  ctx.fillStyle = sweep;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.arc(0, 0, maxRadius, -0.09, 0.46);
  ctx.closePath();
  ctx.fill();

  ctx.strokeStyle = "rgba(183, 255, 74, 0.65)";
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(maxRadius, 0);
  ctx.stroke();
  ctx.restore();
}

function animate(time = 0) {
  ctx.clearRect(0, 0, width, height);
  const bg = ctx.createLinearGradient(0, 0, width, height);
  bg.addColorStop(0, "#05070a");
  bg.addColorStop(0.55, "#091112");
  bg.addColorStop(1, "#0d0811");
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, width, height);

  drawGrid(time);
  drawRadar(time);

  nodes.forEach((node, index) => {
    node.x += node.vx;
    node.y += node.vy;

    if (node.x < -20) node.x = width + 20;
    if (node.x > width + 20) node.x = -20;
    if (node.y < -20) node.y = height + 20;
    if (node.y > height + 20) node.y = -20;

    for (let j = index + 1; j < nodes.length; j += 1) {
      const other = nodes[j];
      const dx = node.x - other.x;
      const dy = node.y - other.y;
      const distance = Math.hypot(dx, dy);
      if (distance < 145) {
        ctx.globalAlpha = (1 - distance / 145) * 0.35;
        ctx.strokeStyle = node.color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(node.x, node.y);
        ctx.lineTo(other.x, other.y);
        ctx.stroke();
      }
    }

    if (pointer.active) {
      const dx = node.x - pointer.x;
      const dy = node.y - pointer.y;
      const distance = Math.hypot(dx, dy);
      if (distance < 210) {
        ctx.globalAlpha = (1 - distance / 210) * 0.48;
        ctx.strokeStyle = "#b7ff4a";
        ctx.beginPath();
        ctx.moveTo(pointer.x, pointer.y);
        ctx.lineTo(node.x, node.y);
        ctx.stroke();
      }
    }

    ctx.globalAlpha = 0.9;
    ctx.fillStyle = node.color;
    ctx.beginPath();
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.fill();
  });

  ctx.globalAlpha = 1;
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
animate();

const commandOutput = document.querySelector("#command-output");
const copyButton = document.querySelector("#copy-command");
const intentButtons = document.querySelectorAll(".intent-button");

intentButtons.forEach((button) => {
  button.addEventListener("click", () => {
    intentButtons.forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    commandOutput.textContent = button.dataset.command;
    copyButton.textContent = "复制命令";
  });
});

copyButton.addEventListener("click", async () => {
  const command = commandOutput.textContent;
  try {
    await navigator.clipboard.writeText(command);
    copyButton.textContent = "已复制";
  } catch {
    copyButton.textContent = "复制失败";
  }
});

const installCopyButtons = document.querySelectorAll(".install-copy");

installCopyButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const command = button.closest("article")?.querySelector("code")?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(command);
      button.classList.add("is-copied");
      button.setAttribute("title", "已复制");
      setTimeout(() => {
        button.classList.remove("is-copied");
        button.setAttribute("title", "复制命令");
      }, 1600);
    } catch {
      button.setAttribute("title", "复制失败");
    }
  });
});
