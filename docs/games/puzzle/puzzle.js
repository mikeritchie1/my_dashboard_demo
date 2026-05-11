const board = document.querySelector("#puzzle-board");
const movesEl = document.querySelector("#moves");
const gridSizeEl = document.querySelector("#grid-size");
const statusEl = document.querySelector("#status");
const shuffleButton = document.querySelector("#shuffle-button");
const previewButton = document.querySelector("#preview-button");
const previewImage = document.querySelector("#preview-image");
const imageChoices = document.querySelector("#image-choices");
const sizeSelect = document.querySelector("#size-select");

let imagePath = "images/puzzle.svg";
let puzzleImages = [];
let size = 4;
let tiles = [];
let selectedIndex = -1;
let moves = 0;
let previewVisible = true;

async function loadConfig() {
  let loadedImageCount = 0;
  try {
    const configResponse = await fetch(`config.json?v=${Date.now()}`, { cache: "no-store" });
    if (!configResponse.ok) {
      throw new Error("No config found.");
    }
    const config = await configResponse.json();
    imagePath = String(config.image || imagePath);
    size = Number(config.size || size);
  } catch {
    statusEl.textContent = "Using starter puzzle settings.";
  }

  try {
    const imagesResponse = await fetch(`images.json?v=${Date.now()}`, { cache: "no-store" });
    if (imagesResponse.ok) {
      const imagePayload = await imagesResponse.json();
      puzzleImages = Array.isArray(imagePayload.images) ? imagePayload.images : [];
      loadedImageCount = puzzleImages.length;
    }
  } catch {
    puzzleImages = [];
  }

  size = Math.max(3, Math.min(5, size));
  sizeSelect.value = String(size);
  renderImageOptions();
  previewImage.src = imagePath;
  buildPuzzle();
  statusEl.textContent = `Loaded ${loadedImageCount || 1} puzzle image${(loadedImageCount || 1) === 1 ? "" : "s"}.`;
}

function renderImageOptions() {
  if (!imageChoices) {
    return;
  }
  const images = puzzleImages.length
    ? puzzleImages
    : [{ title: "Starter Puzzle", path: imagePath }];

  if (!images.some((image) => image.path === imagePath)) {
    images.unshift({ title: "Configured Image", path: imagePath });
  }

  imageChoices.innerHTML = "";
  for (const image of images) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "image-choice";
    button.dataset.imagePath = image.path;
    button.title = image.title || image.path;
    button.style.backgroundImage = `url("${image.path}")`;
    if (image.path === imagePath) {
      button.classList.add("is-selected");
    }
    imageChoices.append(button);
  }
}

function buildPuzzle() {
  selectedIndex = -1;
  moves = 0;
  movesEl.textContent = "0";
  gridSizeEl.textContent = `${size}x${size}`;
  tiles = Array.from({ length: size * size }, (_unused, index) => ({
    current: index,
    correct: index,
  }));
  shuffleTiles();
  render();
}

function shuffleTiles() {
  for (let index = tiles.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [tiles[index], tiles[swapIndex]] = [tiles[swapIndex], tiles[index]];
  }
  if (isSolved()) {
    [tiles[0], tiles[1]] = [tiles[1], tiles[0]];
  }
  statusEl.textContent = "Click two pieces to swap them.";
}

function render() {
  board.style.gridTemplateColumns = `repeat(${size}, 1fr)`;
  board.innerHTML = "";
  tiles.forEach((tile, boardIndex) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "puzzle-tile";
    button.dataset.index = String(boardIndex);
    button.style.backgroundImage = `url("${imagePath}")`;
    button.style.backgroundSize = `${size * 100}% ${size * 100}%`;

    const correctX = tile.correct % size;
    const correctY = Math.floor(tile.correct / size);
    const divisor = size - 1 || 1;
    button.style.backgroundPosition = `${(correctX / divisor) * 100}% ${(correctY / divisor) * 100}%`;

    if (boardIndex === selectedIndex) {
      button.classList.add("is-selected");
    }
    if (boardIndex === tile.correct) {
      button.classList.add("is-correct");
    }
    board.append(button);
  });
}

function selectTile(index) {
  if (selectedIndex === -1) {
    selectedIndex = index;
    render();
    return;
  }

  if (selectedIndex === index) {
    selectedIndex = -1;
    render();
    return;
  }

  [tiles[selectedIndex], tiles[index]] = [tiles[index], tiles[selectedIndex]];
  selectedIndex = -1;
  moves += 1;
  movesEl.textContent = String(moves);
  render();

  if (isSolved()) {
    statusEl.textContent = `Solved in ${moves} moves.`;
  }
}

function isSolved() {
  return tiles.every((tile, index) => tile.correct === index);
}

board.addEventListener("click", (event) => {
  const tile = event.target.closest(".puzzle-tile");
  if (!tile) {
    return;
  }
  selectTile(Number(tile.dataset.index));
});

shuffleButton.addEventListener("click", buildPuzzle);

previewButton.addEventListener("click", () => {
  previewVisible = !previewVisible;
  previewImage.classList.toggle("is-hidden", !previewVisible);
  previewButton.textContent = previewVisible ? "Hide Picture" : "Show Picture";
});

sizeSelect.addEventListener("change", (event) => {
  size = Number(event.target.value || 4);
  buildPuzzle();
});

if (imageChoices) {
  imageChoices.addEventListener("click", (event) => {
    const button = event.target.closest("[data-image-path]");
    if (!button) {
      return;
    }
    imagePath = button.dataset.imagePath || imagePath;
    previewImage.src = imagePath;
    renderImageOptions();
    render();
    statusEl.textContent = "Image changed. Piece order kept.";
  });
}

loadConfig();
