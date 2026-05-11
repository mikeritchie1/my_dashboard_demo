const canvas = document.querySelector("#dvd-canvas");
const ctx = canvas.getContext("2d");
const stage = document.querySelector(".dvd-stage");
const fullscreenButton = document.querySelector("#fullscreen-button");
const scoreEl = document.querySelector("#score");
const bestScoreEl = document.querySelector("#best-score");
const logoCountEl = document.querySelector("#logo-count");
const speedLevelEl = document.querySelector("#speed-level");
const energyFillEl = document.querySelector("#energy-fill");
const energyValueEl = document.querySelector("#energy-value");
const pickupFillEl = document.querySelector("#pickup-fill");
const pickupValueEl = document.querySelector("#pickup-value");
const statusEl = document.querySelector("#status");

const storageKey = "my-dashboard:game-lab:dvd-survivor-best";
const logoColors = ["#ff4d6d", "#2dd4bf", "#f7b731", "#7dd3fc", "#f472b6", "#a3e635"];
const survivorRadius = 7;
const logoWidth = 94;
const logoHeight = 52;
const minShieldLength = 18;
const circleStartRadius = 18;
const circleGrowRate = 72;
const circleMaxRadius = 150;
const blobSpawnInterval = 6.5;
const blobRadius = 14;
const maxBlobs = 5;
const maxEnergy = 100;
const energyRechargePerSecond = 65;
const drawEnergyDrainPerSecond = 72;
const circleEnergyDrainPerSecond = 125;
const minActionEnergy = 6;

let logos = [];
let shields = [];
let draftShield = null;
let circles = [];
let chargeCircle = null;
let blobs = [];
let pointer = { x: 0, y: 0, active: false };
let running = false;
let gameOver = false;
let gameOverScore = 0;
let deathFx = null;
let shieldBreakFx = [];
let startedAt = 0;
let lastFrame = 0;
let survivorShieldLayers = 0;
let animationId = 0;
let energy = maxEnergy;
let pickupSpawnTimer = blobSpawnInterval;
let roundPickupCount = 0;
let bestScore = Number(localStorage.getItem(storageKey) || "0");

bestScoreEl.textContent = formatSeconds(bestScore);

function resizeCanvas() {
  const rect = stage.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function stageSize() {
  const rect = stage.getBoundingClientRect();
  return { width: rect.width, height: rect.height };
}

function formatSeconds(value) {
  return `${value.toFixed(1)}s`;
}

function elapsedSeconds(now = performance.now()) {
  return running ? (now - startedAt) / 1000 : 0;
}

function speedMultiplier(seconds) {
  // Tapered growth: rises quickly early, then approaches a soft cap.
  return 1 + 3.2 * (1 - Math.exp(-seconds / 55));
}

function targetLogoCount(seconds) {
  return 1 + Math.floor(seconds / 5);
}

function makeLogo(index = 0) {
  const { width, height } = stageSize();
  const angle = Math.random() * Math.PI * 2;
  const baseSpeed = 120 + Math.random() * 60 + index * 7;
  let x = Math.random() * Math.max(1, width - logoWidth);
  let y = Math.random() * Math.max(1, height - logoHeight);
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const dx = pointer.x - (x + logoWidth / 2);
    const dy = pointer.y - (y + logoHeight / 2);
    if (!pointer.active || Math.hypot(dx, dy) > 150) {
      break;
    }
    x = Math.random() * Math.max(1, width - logoWidth);
    y = Math.random() * Math.max(1, height - logoHeight);
  }
  return {
    x,
    y,
    vx: Math.cos(angle) * baseSpeed,
    vy: Math.sin(angle) * baseSpeed,
    width: logoWidth,
    height: logoHeight,
    color: logoColors[index % logoColors.length],
  };
}

function startGame() {
  resizeCanvas();
  const { width, height } = stageSize();
  pointer = { x: width / 2, y: height / 2, active: true };
  logos = logos.length ? [logos[0]] : [makeLogo(0)];
  shields = [];
  draftShield = null;
  circles = [];
  chargeCircle = null;
  blobs = [];
  survivorShieldLayers = 0;
  shieldBreakFx = [];
  energy = maxEnergy;
  pickupSpawnTimer = blobSpawnInterval;
  roundPickupCount = 0;
  updatePickupUi();
  updateEnergyUi();
  running = true;
  gameOver = false;
  gameOverScore = 0;
  startedAt = performance.now();
  lastFrame = startedAt;
  statusEl.textContent = "Survive.";
  window.cancelAnimationFrame(animationId);
  animationId = window.requestAnimationFrame(loop);
}

function endGame(now, killerLogo = null) {
  const finalScore = (now - startedAt) / 1000;
  const keptLogo = killerLogo || (logos.length ? logos[Math.floor(Math.random() * logos.length)] : null);
  running = false;
  gameOver = true;
  gameOverScore = finalScore;
  if (finalScore > bestScore) {
    bestScore = finalScore;
    localStorage.setItem(storageKey, String(bestScore));
    bestScoreEl.textContent = formatSeconds(bestScore);
  }
  shields = [];
  draftShield = null;
  circles = [];
  chargeCircle = null;
  blobs = [];
  survivorShieldLayers = 0;
  shieldBreakFx = [];
  energy = maxEnergy;
  pickupSpawnTimer = blobSpawnInterval;
  updateEnergyUi();

  if (keptLogo) {
    const magnitude = Math.hypot(keptLogo.vx, keptLogo.vy) || 1;
    const baseSpeed = 120;
    keptLogo.vx = (keptLogo.vx / magnitude) * baseSpeed;
    keptLogo.vy = (keptLogo.vy / magnitude) * baseSpeed;
    logos = [keptLogo];
  } else {
    logos = [makeLogo(0)];
  }

  scoreEl.textContent = "0.0s";
  logoCountEl.textContent = "1";
  speedLevelEl.textContent = String(roundPickupCount);
  statusEl.textContent = `Hit. Survived ${formatSeconds(finalScore)}.`;
  deathFx = createDeathFx(pointer.x, pointer.y, now);
}

function loop(now) {
  resizeCanvas();
  const dt = Math.min(0.034, (now - lastFrame) / 1000 || 0);
  lastFrame = now;
  const seconds = elapsedSeconds(now);
  const multiplier = running ? speedMultiplier(seconds) : 1;

  if (!logos.length) {
    logos = [makeLogo(0)];
  }
  if (running) {
    while (logos.length < targetLogoCount(seconds)) {
      logos.push(makeLogo(logos.length));
    }
    updatePickupSpawn(dt);
  }

  updateEnergy(dt);
  updateLogos(dt, multiplier);
  handleShieldCollisions();
  updateChargeCircle(seconds);
  handleChargeCircleCollisions(running);
  if (running) {
    collectBlobs(seconds);
  }
  updateShieldBreakFx(now);
  updateDeathFx(now);
  draw(seconds, multiplier);

  if (pointer.active && !handleSurvivorLogoInteractions(now)) {
    animationId = window.requestAnimationFrame(loop);
    return;
  }

  scoreEl.textContent = formatSeconds(running ? seconds : 0);
  logoCountEl.textContent = String(logos.length);
  speedLevelEl.textContent = String(roundPickupCount);
  animationId = window.requestAnimationFrame(loop);
}

function createDeathFx(x, y, now) {
  const { width, height } = stageSize();
  const offscreenDistance = Math.hypot(width, height) * 0.95;
  const particles = [];
  const particleCount = 38;
  const life = 1.2;
  for (let index = 0; index < particleCount; index += 1) {
    const angle = (Math.PI * 2 * index) / particleCount + Math.random() * 0.3;
    const speed = 280 + Math.random() * 260;
    particles.push({
      ox: x,
      oy: y,
      x,
      y,
      dx: Math.cos(angle),
      dy: Math.sin(angle),
      speed,
      far: offscreenDistance + Math.random() * 120,
      life,
      age: 0,
      size: 2 + Math.random() * 3,
    });
  }
  return {
    startedAt: now,
    lastUpdateAt: now,
    flashDuration: 170,
    particles,
    outwardDuration: 0.34,
    duration: 1250,
  };
}

function updateDeathFx(now) {
  if (!deathFx) {
    return;
  }
  const elapsed = now - deathFx.startedAt;
  const dt = Math.min(0.034, (now - deathFx.lastUpdateAt) / 1000 || 0.016);
  deathFx.lastUpdateAt = now;
  for (const particle of deathFx.particles) {
    particle.age += dt;
    const t = Math.min(1, particle.age / particle.life);
    if (t <= deathFx.outwardDuration) {
      const outwardT = t / deathFx.outwardDuration;
      const distance = particle.far * outwardT;
      particle.x = particle.ox + particle.dx * distance;
      particle.y = particle.oy + particle.dy * distance;
    } else {
      const returnT = (t - deathFx.outwardDuration) / (1 - deathFx.outwardDuration);
      const farX = particle.ox + particle.dx * particle.far;
      const farY = particle.oy + particle.dy * particle.far;
      const targetX = pointer.x;
      const targetY = pointer.y;
      particle.x = farX + (targetX - farX) * returnT;
      particle.y = farY + (targetY - farY) * returnT;
    }
  }
  if (elapsed >= deathFx.duration) {
    deathFx = null;
    gameOver = false;
    statusEl.textContent = `Click anywhere to start again. Best ${formatSeconds(bestScore)}.`;
  }
}

function spawnShieldBreakFx(x, y, now) {
  const particles = [];
  const particleCount = 14;
  for (let index = 0; index < particleCount; index += 1) {
    const angle = (Math.PI * 2 * index) / particleCount + Math.random() * 0.4;
    const speed = 70 + Math.random() * 130;
    particles.push({
      x,
      y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      life: 0.28 + Math.random() * 0.24,
      age: 0,
      size: 1.4 + Math.random() * 2.1,
    });
  }
  shieldBreakFx.push({
    lastUpdateAt: now,
    particles,
  });
}

function updateShieldBreakFx(now) {
  if (!shieldBreakFx.length) {
    return;
  }
  for (let fxIndex = shieldBreakFx.length - 1; fxIndex >= 0; fxIndex -= 1) {
    const fx = shieldBreakFx[fxIndex];
    const dt = Math.min(0.034, (now - fx.lastUpdateAt) / 1000 || 0.016);
    fx.lastUpdateAt = now;
    for (const particle of fx.particles) {
      particle.age += dt;
      particle.x += particle.vx * dt;
      particle.y += particle.vy * dt;
      particle.vx *= 0.975;
      particle.vy *= 0.975;
    }
    fx.particles = fx.particles.filter((particle) => particle.age < particle.life);
    if (!fx.particles.length) {
      shieldBreakFx.splice(fxIndex, 1);
    }
  }
}

function updatePickupSpawn(dt) {
  if (blobs.length > 0) {
    updatePickupUi();
    return;
  }
  pickupSpawnTimer = Math.max(0, pickupSpawnTimer - dt);
  if (pickupSpawnTimer <= 0 && blobs.length < maxBlobs) {
    blobs.push(makeBlob());
    pickupSpawnTimer = 0;
  }
  updatePickupUi();
}

function makeBlob() {
  const { width, height } = stageSize();
  const margin = 46;
  const minX = margin;
  const minY = margin;
  const maxX = Math.max(minX, width - margin);
  const maxY = Math.max(minY, height - margin);
  return {
    x: minX + Math.random() * Math.max(1, maxX - minX),
    y: minY + Math.random() * Math.max(1, maxY - minY),
    phase: Math.random() * Math.PI * 2,
  };
}

function collectBlobs(seconds) {
  if (!pointer.active) {
    return;
  }
  for (let index = blobs.length - 1; index >= 0; index -= 1) {
    const blob = blobs[index];
    const dx = pointer.x - blob.x;
    const dy = pointer.y - blob.y;
    if (dx * dx + dy * dy <= (blobRadius + survivorRadius) * (blobRadius + survivorRadius)) {
      blobs.splice(index, 1);
      survivorShieldLayers += 1;
      roundPickupCount += 1;
      pickupSpawnTimer = blobSpawnInterval;
      updatePickupUi();
      statusEl.textContent = `Shield layer +1 (${survivorShieldLayers}).`;
    }
  }
}

function handleSurvivorLogoInteractions(now) {
  for (let index = logos.length - 1; index >= 0; index -= 1) {
    const logo = logos[index];
    if (!hitsSurvivor(logo)) {
      continue;
    }
    if (!running) {
      bounceLogoFromSurvivorMenu(logo);
      continue;
    }
    if (survivorShieldLayers > 0) {
      spawnShieldBreakFx(pointer.x, pointer.y, now);
      survivorShieldLayers -= 1;
      logos.splice(index, 1);
      statusEl.textContent = `Shield absorbed hit (${survivorShieldLayers} left).`;
      continue;
    }
    endGame(now, logo);
    return false;
  }
  return true;
}

function bounceLogoFromSurvivorMenu(logo) {
  const centerX = logo.x + logo.width / 2;
  const centerY = logo.y + logo.height / 2;
  const dx = centerX - pointer.x;
  const dy = centerY - pointer.y;
  const length = Math.hypot(dx, dy) || 1;
  const nx = dx / length;
  const ny = dy / length;
  const dot = logo.vx * nx + logo.vy * ny;
  if (dot < 0) {
    logo.vx -= 2 * dot * nx;
    logo.vy -= 2 * dot * ny;
  }
  const baseSpeed = 120;
  const speed = Math.hypot(logo.vx, logo.vy) || 1;
  logo.vx = (logo.vx / speed) * baseSpeed;
  logo.vy = (logo.vy / speed) * baseSpeed;
  logo.x += nx * 10;
  logo.y += ny * 10;
}

function updateLogos(dt, multiplier) {
  const { width, height } = stageSize();
  for (const logo of logos) {
    logo.x += logo.vx * multiplier * dt;
    logo.y += logo.vy * multiplier * dt;

    if (logo.x <= 0 || logo.x + logo.width >= width) {
      logo.x = Math.max(0, Math.min(width - logo.width, logo.x));
      logo.vx *= -1;
      logo.color = logoColors[Math.floor(Math.random() * logoColors.length)];
    }

    if (logo.y <= 0 || logo.y + logo.height >= height) {
      logo.y = Math.max(0, Math.min(height - logo.height, logo.y));
      logo.vy *= -1;
      logo.color = logoColors[Math.floor(Math.random() * logoColors.length)];
    }
  }
}

function updateEnergy(dt) {
  if (!running) {
    energy = maxEnergy;
    updateEnergyUi();
    return;
  }
  let drain = 0;
  if (draftShield) {
    drain += drawEnergyDrainPerSecond * dt;
  }
  if (chargeCircle) {
    drain += circleEnergyDrainPerSecond * dt;
  }

  if (drain > 0) {
    energy = Math.max(0, energy - drain);
  } else {
    energy = Math.min(maxEnergy, energy + energyRechargePerSecond * dt);
  }

  if (energy <= 0 && draftShield) {
    placeDraftShield();
    statusEl.textContent = "Energy empty.";
  }
  if (energy <= 0 && chargeCircle) {
    circles.push({ ...chargeCircle });
    chargeCircle = null;
    statusEl.textContent = "Energy empty.";
  }

  updateEnergyUi();
}

function updateEnergyUi() {
  const energyPercent = Math.round(energy);
  if (energyFillEl) {
    energyFillEl.style.width = `${energyPercent}%`;
  }
  if (energyValueEl) {
    energyValueEl.textContent = `${energyPercent}%`;
  }
}

function updatePickupUi() {
  const activePickup = blobs.length > 0;
  const timerValue = activePickup ? 0 : pickupSpawnTimer;
  const progress = activePickup ? 100 : ((blobSpawnInterval - timerValue) / blobSpawnInterval) * 100;
  if (pickupFillEl) {
    pickupFillEl.style.width = `${Math.max(0, Math.min(100, progress))}%`;
  }
  if (pickupValueEl) {
    pickupValueEl.textContent = activePickup ? "Ready" : `${timerValue.toFixed(1)}s`;
  }
  if (speedLevelEl) {
    speedLevelEl.textContent = String(roundPickupCount);
  }
}

function survivorCollisionRadius() {
  if (survivorShieldLayers <= 0) {
    return survivorRadius;
  }
  return survivorRadius + 6 + (survivorShieldLayers - 1) * 4;
}

function hitsSurvivor(logo) {
  const radius = survivorCollisionRadius();
  const closestX = Math.max(logo.x, Math.min(pointer.x, logo.x + logo.width));
  const closestY = Math.max(logo.y, Math.min(pointer.y, logo.y + logo.height));
  const dx = pointer.x - closestX;
  const dy = pointer.y - closestY;
  return dx * dx + dy * dy <= radius * radius;
}

function handleShieldCollisions() {
  for (const logo of logos) {
    const draftHit = draftShield ? logoHitsPath(logo, draftShield) : null;
    if (draftHit) {
      reflectLogoFromShield(logo, draftHit);
      draftShield = { points: [{ x: pointer.x, y: pointer.y }] };
      statusEl.textContent = "Drawing shield broke.";
      continue;
    }

    const hitIndex = shields.findIndex((shieldPath) => logoHitsPath(logo, shieldPath));
    if (hitIndex !== -1) {
      const hitSegment = logoHitsPath(logo, shields[hitIndex]);
      if (hitSegment) {
        reflectLogoFromShield(logo, hitSegment);
      }
      shields.splice(hitIndex, 1);
    }
  }
}

function logoHitsPath(logo, path) {
  if (!path || !Array.isArray(path.points) || path.points.length < 2) {
    return null;
  }
  for (let index = 1; index < path.points.length; index += 1) {
    const previous = path.points[index - 1];
    const current = path.points[index];
    const segment = { x1: previous.x, y1: previous.y, x2: current.x, y2: current.y };
    if (logoHitsShield(logo, segment)) {
      return segment;
    }
  }
  return null;
}

function updateChargeCircle(seconds) {
  if (!chargeCircle) {
    return;
  }
  chargeCircle.x = pointer.x;
  chargeCircle.y = pointer.y;
  chargeCircle.radius = Math.min(
    circleMaxRadius,
    circleStartRadius + (seconds - chargeCircle.startedAt) * circleGrowRate,
    containedCircleRadius(chargeCircle.x, chargeCircle.y),
  );
}

function handleChargeCircleCollisions(isLethal) {
  if (chargeCircle) {
    const hitLogo = logos.find((logo) => logoHitsCircle(logo, chargeCircle));
    if (hitLogo) {
      reflectLogoFromCircle(hitLogo, chargeCircle);
      if (isLethal) {
        chargeCircle = null;
        statusEl.textContent = "Circle broke.";
      }
    }
  }

  for (const logo of logos) {
    const hitIndex = circles.findIndex((circle) => logoHitsCircle(logo, circle));
    if (hitIndex === -1) {
      continue;
    }
    reflectLogoFromCircle(logo, circles[hitIndex]);
    if (isLethal) {
      circles.splice(hitIndex, 1);
      statusEl.textContent = "Circle broke.";
    }
  }
}

function logoHitsCircle(logo, circle) {
  const closestX = Math.max(logo.x, Math.min(circle.x, logo.x + logo.width));
  const closestY = Math.max(logo.y, Math.min(circle.y, logo.y + logo.height));
  const dx = circle.x - closestX;
  const dy = circle.y - closestY;
  return dx * dx + dy * dy <= circle.radius * circle.radius;
}

function reflectLogoFromCircle(logo, circle) {
  const centerX = logo.x + logo.width / 2;
  const centerY = logo.y + logo.height / 2;
  const dx = centerX - circle.x;
  const dy = centerY - circle.y;
  const length = Math.hypot(dx, dy) || 1;
  const nx = dx / length;
  const ny = dy / length;
  const dot = logo.vx * nx + logo.vy * ny;
  if (dot < 0) {
    logo.vx -= 2 * dot * nx;
    logo.vy -= 2 * dot * ny;
  }
  logo.vx += nx * 95;
  logo.vy += ny * 95;
  logo.x += nx * 18;
  logo.y += ny * 18;
  logo.color = "#ffffff";
}

function logoHitsShield(logo, shield) {
  const points = [
    { x: logo.x, y: logo.y },
    { x: logo.x + logo.width, y: logo.y },
    { x: logo.x + logo.width, y: logo.y + logo.height },
    { x: logo.x, y: logo.y + logo.height },
    { x: logo.x + logo.width / 2, y: logo.y + logo.height / 2 },
  ];
  return points.some((point) => distanceToSegment(point, shield) <= 8)
    || segmentIntersectsRect(shield, logo);
}

function distanceToSegment(point, segment) {
  const dx = segment.x2 - segment.x1;
  const dy = segment.y2 - segment.y1;
  const lengthSq = dx * dx + dy * dy;
  if (!lengthSq) {
    return Math.hypot(point.x - segment.x1, point.y - segment.y1);
  }
  const t = Math.max(0, Math.min(1, ((point.x - segment.x1) * dx + (point.y - segment.y1) * dy) / lengthSq));
  const projectedX = segment.x1 + t * dx;
  const projectedY = segment.y1 + t * dy;
  return Math.hypot(point.x - projectedX, point.y - projectedY);
}

function segmentIntersectsRect(segment, rect) {
  const corners = [
    { x: rect.x, y: rect.y },
    { x: rect.x + rect.width, y: rect.y },
    { x: rect.x + rect.width, y: rect.y + rect.height },
    { x: rect.x, y: rect.y + rect.height },
  ];
  const edges = [
    [corners[0], corners[1]],
    [corners[1], corners[2]],
    [corners[2], corners[3]],
    [corners[3], corners[0]],
  ];
  return edges.some(([a, b]) => segmentsIntersect(
    { x: segment.x1, y: segment.y1 },
    { x: segment.x2, y: segment.y2 },
    a,
    b,
  ));
}

function segmentsIntersect(a, b, c, d) {
  const cross1 = cross(a, b, c);
  const cross2 = cross(a, b, d);
  const cross3 = cross(c, d, a);
  const cross4 = cross(c, d, b);
  return cross1 * cross2 <= 0 && cross3 * cross4 <= 0;
}

function cross(a, b, c) {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function reflectLogoFromShield(logo, shield) {
  const dx = shield.x2 - shield.x1;
  const dy = shield.y2 - shield.y1;
  const length = Math.hypot(dx, dy) || 1;
  let nx = -dy / length;
  let ny = dx / length;
  const dot = logo.vx * nx + logo.vy * ny;
  logo.vx -= 2 * dot * nx;
  logo.vy -= 2 * dot * ny;
  logo.vx *= 1.04;
  logo.vy *= 1.04;
  const pushDirection = dot > 0 ? -1 : 1;
  logo.x += nx * pushDirection * 12;
  logo.y += ny * pushDirection * 12;
  logo.color = "#ffffff";
}

function draw(seconds, multiplier) {
  const { width, height } = stageSize();
  ctx.clearRect(0, 0, width, height);
  drawBackground(width, height);
  const dangerAmount = Math.max(0, Math.min(1, (multiplier - 1) / 3.2));
  for (const logo of logos) {
    drawLogo(logo, dangerAmount);
  }
  drawBlobs(seconds);
  drawShields();
  drawChargeCircle();
  drawSurvivor();
  drawShieldBreakFx();
  drawDeathFx();

  if (!running && !gameOver) {
    drawPreStartOverlay();
  }
}

function drawBlobs(seconds) {
  for (const blob of blobs) {
    const pulse = 0.55 + 0.45 * Math.sin(seconds * 2.8 + blob.phase);
    const radius = blobRadius + pulse * 4;
    const alpha = 0.2 + 0.35 * pulse;
    ctx.save();
    ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
    ctx.shadowColor = "rgba(255, 255, 255, 0.75)";
    ctx.shadowBlur = 18 + pulse * 12;
    ctx.beginPath();
    ctx.arc(blob.x, blob.y, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

function drawBackground(width, height) {
  ctx.fillStyle = "#080b10";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.055)";
  ctx.lineWidth = 1;
  for (let x = 0; x < width; x += 38) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }
  for (let y = 0; y < height; y += 38) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
}

function drawLogo(logo, dangerAmount = 0) {
  ctx.save();
  ctx.translate(logo.x, logo.y);
  ctx.fillStyle = blendTowardRed(logo.color, dangerAmount);
  roundRect(0, 0, logo.width, logo.height, 10);
  ctx.fill();
  ctx.fillStyle = "#06080d";
  ctx.font = "900 23px Trebuchet MS, Verdana, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("DVD", logo.width / 2, logo.height / 2 - 3);
  ctx.font = "800 9px Trebuchet MS, Verdana, sans-serif";
  ctx.fillText("VIDEO", logo.width / 2, logo.height / 2 + 15);
  ctx.restore();
}

function blendTowardRed(hexColor, amount) {
  const normalized = hexColor.replace("#", "");
  const full = normalized.length === 3
    ? normalized.split("").map((ch) => ch + ch).join("")
    : normalized;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  const t = Math.max(0, Math.min(1, amount));
  const nr = Math.round(r + (255 - r) * t);
  const ng = Math.round(g * (1 - t));
  const nb = Math.round(b * (1 - t));
  return `rgb(${nr}, ${ng}, ${nb})`;
}

function drawShields() {
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const shield of shields) {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.92)";
    ctx.lineWidth = 5;
    drawPath(shield);
  }
  if (draftShield) {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.64)";
    ctx.lineWidth = 4;
    drawPath(draftShield);
  }
  ctx.restore();
}

function drawPath(path) {
  if (!path || !Array.isArray(path.points) || path.points.length < 2) {
    return;
  }
  ctx.beginPath();
  ctx.moveTo(path.points[0].x, path.points[0].y);
  for (let index = 1; index < path.points.length; index += 1) {
    ctx.lineTo(path.points[index].x, path.points[index].y);
  }
  ctx.stroke();
}

function drawChargeCircle() {
  for (const circle of circles) {
    drawCircle(circle, "rgba(255, 255, 255, 0.78)", "rgba(255, 255, 255, 0.06)");
  }
  if (!chargeCircle) {
    return;
  }
  drawCircle(chargeCircle, "rgba(255, 255, 255, 0.86)", "rgba(255, 255, 255, 0.08)");
}

function drawCircle(circle, strokeStyle, fillStyle) {
  ctx.save();
  ctx.strokeStyle = strokeStyle;
  ctx.fillStyle = fillStyle;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(circle.x, circle.y, circle.radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawSurvivor() {
  if (!pointer.active) {
    return;
  }
  if (deathFx) {
    return;
  }
  ctx.save();
  for (let layer = 0; layer < survivorShieldLayers; layer += 1) {
    ctx.strokeStyle = "rgba(255, 255, 255, 0.8)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(pointer.x, pointer.y, survivorRadius + 6 + layer * 4, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#0d1117";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(pointer.x, pointer.y, survivorRadius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

function drawPreStartOverlay() {
  const { width, height } = stageSize();
  const panelWidth = Math.min(560, width - 40);
  const panelHeight = 150;
  const panelX = (width - panelWidth) / 2;
  const panelY = (height - panelHeight) / 2 - 18;
  ctx.save();
  ctx.fillStyle = "rgba(8, 11, 16, 0.72)";
  roundRect(panelX, panelY, panelWidth, panelHeight, 12);
  ctx.fill();
  ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
  ctx.font = "900 30px Trebuchet MS, Verdana, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("Click Anywhere To Start", width / 2, panelY + 36);
  ctx.font = "700 16px Trebuchet MS, Verdana, sans-serif";
  ctx.fillStyle = "rgba(255, 255, 255, 0.84)";
  ctx.fillText("Left Click: Draw line shield", width / 2, panelY + 76);
  ctx.fillText("Right Click: Grow circle shield", width / 2, panelY + 100);
  ctx.fillText("Pickups: Collect glowing orbs for hit-protect shields", width / 2, panelY + 124);
  ctx.restore();
}

function drawDeathFx() {
  if (!deathFx) {
    return;
  }
  const now = performance.now();
  const elapsed = now - deathFx.startedAt;
  const flashAlpha = Math.max(0, 1 - elapsed / deathFx.flashDuration) * 0.72;
  if (flashAlpha > 0) {
    const { width, height } = stageSize();
    ctx.save();
    ctx.fillStyle = `rgba(255, 255, 255, ${flashAlpha})`;
    ctx.fillRect(0, 0, width, height);
    ctx.restore();
  }
  ctx.save();
  for (const particle of deathFx.particles) {
    ctx.fillStyle = "rgba(255, 255, 255, 1)";
    ctx.beginPath();
    ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawShieldBreakFx() {
  if (!shieldBreakFx.length) {
    return;
  }
  ctx.save();
  for (const fx of shieldBreakFx) {
    for (const particle of fx.particles) {
      const alpha = Math.max(0, 1 - particle.age / particle.life);
      ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.9})`;
      ctx.beginPath();
      ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();
}

function roundRect(x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

function updatePointer(event) {
  const rect = canvas.getBoundingClientRect();
  const rawX = event.clientX - rect.left;
  const rawY = event.clientY - rect.top;
  const projected = projectPointerToPlayfield(rawX, rawY, rect.width, rect.height);
  pointer.x = projected.x;
  pointer.y = projected.y;
  pointer.active = true;
}

function projectPointerToPlayfield(rawX, rawY, width, height) {
  const minX = survivorRadius;
  const minY = survivorRadius;
  const maxX = Math.max(minX, width - survivorRadius);
  const maxY = Math.max(minY, height - survivorRadius);
  const isInsideCanvas = rawX >= 0 && rawX <= width && rawY >= 0 && rawY <= height;

  if (isInsideCanvas) {
    return {
      x: Math.max(minX, Math.min(maxX, rawX)),
      y: Math.max(minY, Math.min(maxY, rawY)),
    };
  }

  const centerX = width / 2;
  const centerY = height / 2;
  const dx = rawX - centerX;
  const dy = rawY - centerY;
  const candidates = [];

  if (dx !== 0) {
    candidates.push((minX - centerX) / dx);
    candidates.push((maxX - centerX) / dx);
  }
  if (dy !== 0) {
    candidates.push((minY - centerY) / dy);
    candidates.push((maxY - centerY) / dy);
  }

  for (const t of candidates.filter((value) => value > 0).sort((a, b) => a - b)) {
    const x = centerX + dx * t;
    const y = centerY + dy * t;
    if (x >= minX - 0.01 && x <= maxX + 0.01 && y >= minY - 0.01 && y <= maxY + 0.01) {
      return {
        x: Math.max(minX, Math.min(maxX, x)),
        y: Math.max(minY, Math.min(maxY, y)),
      };
    }
  }

  return { x: centerX, y: centerY };
}

function containedCircleRadius(x, y) {
  const { width, height } = stageSize();
  return Math.max(0, Math.min(x, y, width - x, height - y));
}

function addPointToDraftShield(x, y) {
  if (!draftShield || !Array.isArray(draftShield.points)) {
    return;
  }
  const lastPoint = draftShield.points[draftShield.points.length - 1];
  if (!lastPoint || Math.hypot(x - lastPoint.x, y - lastPoint.y) >= 4) {
    draftShield.points.push({ x, y });
  }
}

function pathLength(path) {
  if (!path || !Array.isArray(path.points) || path.points.length < 2) {
    return 0;
  }
  let total = 0;
  for (let index = 1; index < path.points.length; index += 1) {
    const previous = path.points[index - 1];
    const current = path.points[index];
    total += Math.hypot(current.x - previous.x, current.y - previous.y);
  }
  return total;
}

function placeDraftShield() {
  if (!draftShield) {
    return;
  }
  addPointToDraftShield(pointer.x, pointer.y);
  if (pathLength(draftShield) >= minShieldLength) {
    shields.push(draftShield);
    statusEl.textContent = "Shield placed.";
  }
  draftShield = null;
}

stage.addEventListener("pointermove", (event) => {
  updatePointer(event);
  if (draftShield) {
    addPointToDraftShield(pointer.x, pointer.y);
  }
  if (chargeCircle) {
    chargeCircle.x = pointer.x;
    chargeCircle.y = pointer.y;
  }
});
stage.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  updatePointer(event);
  if (gameOver) {
    return;
  }
  if (!running) {
    startGame();
    return;
  }
  if (event.button === 2) {
    if (running && energy < minActionEnergy) {
      statusEl.textContent = "Not enough energy.";
      return;
    }
    chargeCircle = {
      x: pointer.x,
      y: pointer.y,
      radius: circleStartRadius,
      startedAt: elapsedSeconds(),
    };
    stage.setPointerCapture(event.pointerId);
    return;
  }
  if (running && energy < minActionEnergy) {
    statusEl.textContent = "Not enough energy.";
    return;
  }
  draftShield = { points: [{ x: pointer.x, y: pointer.y }] };
  stage.setPointerCapture(event.pointerId);
});

stage.addEventListener("pointerup", (event) => {
  event.preventDefault();
  updatePointer(event);
  if (event.button === 2) {
    if (chargeCircle) {
      circles.push({ ...chargeCircle });
      statusEl.textContent = "Circle placed.";
      chargeCircle = null;
    }
    if (stage.hasPointerCapture(event.pointerId)) {
      stage.releasePointerCapture(event.pointerId);
    }
    return;
  }
  if (draftShield) {
    placeDraftShield();
  }
  if (stage.hasPointerCapture(event.pointerId)) {
    stage.releasePointerCapture(event.pointerId);
  }
});

window.addEventListener("pointermove", (event) => {
  updatePointer(event);
  if (draftShield) {
    addPointToDraftShield(pointer.x, pointer.y);
  }
  if (chargeCircle) {
    chargeCircle.x = pointer.x;
    chargeCircle.y = pointer.y;
  }
});

stage.addEventListener("pointerleave", (event) => {
  updatePointer(event);
  if (!stage.hasPointerCapture(event.pointerId)) {
    draftShield = null;
    chargeCircle = null;
  }
});

stage.addEventListener("contextmenu", (event) => {
  event.preventDefault();
});

if (fullscreenButton) {
  fullscreenButton.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await document.documentElement.requestFullscreen();
      }
    } catch {
      statusEl.textContent = "Fullscreen blocked by browser.";
    }
  });
}

document.addEventListener("fullscreenchange", () => {
  if (fullscreenButton) {
    fullscreenButton.textContent = document.fullscreenElement ? "Exit Fullscreen" : "Fullscreen";
  }
  resizeCanvas();
  draw(elapsedSeconds(), speedMultiplier(elapsedSeconds()));
});

window.addEventListener("resize", () => {
  resizeCanvas();
  draw(0, 1);
});

resizeCanvas();
{
  const { width, height } = stageSize();
  pointer = { x: width / 2, y: height / 2, active: true };
  logos = [makeLogo(0)];
  lastFrame = performance.now();
}
updateEnergyUi();
updatePickupUi();
draw(0, 1);
animationId = window.requestAnimationFrame(loop);
