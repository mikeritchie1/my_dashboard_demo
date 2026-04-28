const CSV_PATH = "data/all_stores_missing_available.csv";
const NEW_CARDS_PATH = "data/new_missing_cards.json";

const state = {
  rows: [],
  newCardKeys: new Set(),
  search: "",
  store: "",
  rarity: "",
  minPrice: 0,
  maxPrice: 200,
  section: "one-piece",
};

const elements = {
  onePieceSection: document.querySelector("#one-piece-section"),
  eventsSection: document.querySelector("#events-section"),
  sectionFilter: document.querySelector("#section-filter"),
  body: document.querySelector("#cards-body"),
  listingCount: document.querySelector("#listing-count"),
  cardCount: document.querySelector("#card-count"),
  storeCount: document.querySelector("#store-count"),
  cheapestPrice: document.querySelector("#cheapest-price"),
  search: document.querySelector("#search"),
  storeFilter: document.querySelector("#store-filter"),
  rarityFilter: document.querySelector("#rarity-filter"),
  minPrice: document.querySelector("#min-price"),
  maxPrice: document.querySelector("#max-price"),
};

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (quoted && char === '"' && next === '"') {
      value += '"';
      index += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (!quoted && char === ",") {
      row.push(value);
      value = "";
    } else if (!quoted && (char === "\n" || char === "\r")) {
      if (char === "\r" && next === "\n") {
        index += 1;
      }
      row.push(value);
      if (row.some((cell) => cell !== "")) {
        rows.push(row);
      }
      row = [];
      value = "";
    } else {
      value += char;
    }
  }

  if (value || row.length) {
    row.push(value);
    rows.push(row);
  }

  const headers = rows.shift() || [];
  return rows.map((cells) =>
    Object.fromEntries(headers.map((header, index) => [header, cells[index] || ""])),
  );
}

function money(value) {
  const amount = Number.parseFloat(value || "0");
  return `R ${amount.toFixed(2)}`;
}

function rowKey(row) {
  return [row.card_number, row.store, row.url].map((value) => (value || "").trim()).join("|");
}

function unique(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function optionList(select, values, label) {
  select.innerHTML = `<option value="">${label}</option>`;
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
}

function filteredRows() {
  const term = state.search.trim().toLowerCase();
  return state.rows.filter((row) => {
    const price = Number.parseFloat(row.price || "0");
    const matchesStore = !state.store || row.store === state.store;
    const matchesRarity = !state.rarity || row.rarity === state.rarity;
    const matchesMinPrice = !Number.isFinite(state.minPrice) || price >= state.minPrice;
    const matchesMaxPrice = !Number.isFinite(state.maxPrice) || price <= state.maxPrice;
    const haystack = [
      row.card_number,
      row.title,
      row.rarity,
      row.store,
      row.set_name,
      row.stock,
    ]
      .join(" ")
      .toLowerCase();
    const matchesSearch = !term || haystack.includes(term);
    return matchesStore && matchesRarity && matchesMinPrice && matchesMaxPrice && matchesSearch;
  });
}

function renderSummary(rows) {
  const cards = unique(rows.map((row) => row.card_number));
  const stores = unique(rows.map((row) => row.store));
  const prices = rows.map((row) => Number.parseFloat(row.price || "0")).filter(Number.isFinite);

  elements.listingCount.textContent = rows.length.toString();
  elements.cardCount.textContent = cards.length.toString();
  elements.storeCount.textContent = stores.length.toString();
  elements.cheapestPrice.textContent = prices.length ? money(Math.min(...prices)) : "R 0.00";
}

function renderTable(rows) {
  if (!rows.length) {
    elements.body.innerHTML = '<tr><td colspan="7" class="empty">No cards match the filters.</td></tr>';
    return;
  }

  elements.body.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    const isNew = state.newCardKeys.has(rowKey(row));
    if (isNew) {
      tr.classList.add("new-card-row");
    }
    tr.innerHTML = `
      <td class="card-number"></td>
      <td class="price"></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>
    `;

    const cells = tr.querySelectorAll("td");
    cells[0].textContent = row.card_number;
    cells[1].textContent = money(row.price);
    cells[2].textContent = row.title;
    cells[3].textContent = row.rarity || "-";
    cells[4].textContent = row.store;
    cells[5].textContent = row.stock || "-";

    if (isNew) {
      const badge = document.createElement("span");
      badge.className = "new-badge";
      badge.textContent = "New";
      cells[2].prepend(badge);
    }

    const link = document.createElement("a");
    link.className = "buy-link";
    link.href = row.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "Open";
    cells[6].append(link);

    elements.body.append(tr);
  }
}

function render() {
  elements.onePieceSection.hidden = state.section !== "one-piece";
  elements.eventsSection.hidden = state.section !== "events";

  if (state.section !== "one-piece") {
    return;
  }

  const rows = filteredRows().sort((left, right) => {
    const price = Number.parseFloat(left.price || "0") - Number.parseFloat(right.price || "0");
    if (price !== 0) {
      return price;
    }
    return `${left.card_number} ${left.store} ${left.title}`.localeCompare(
      `${right.card_number} ${right.store} ${right.title}`,
    );
  });

  renderSummary(rows);
  renderTable(rows);
}

async function load() {
  try {
    const response = await fetch(CSV_PATH, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Could not load ${CSV_PATH}`);
    }
    state.rows = parseCsv(await response.text());
    try {
      const newCardsResponse = await fetch(NEW_CARDS_PATH, { cache: "no-store" });
      if (newCardsResponse.ok) {
        const payload = await newCardsResponse.json();
        state.newCardKeys = new Set(payload.keys || []);
      }
    } catch {
      state.newCardKeys = new Set();
    }
    optionList(elements.storeFilter, unique(state.rows.map((row) => row.store)), "All stores");
    optionList(elements.rarityFilter, unique(state.rows.map((row) => row.rarity)), "All rarities");
    render();
  } catch (error) {
    elements.body.innerHTML = `<tr><td colspan="7" class="empty">${error.message}</td></tr>`;
  }
}

elements.search.addEventListener("input", (event) => {
  state.search = event.target.value;
  render();
});

elements.storeFilter.addEventListener("change", (event) => {
  state.store = event.target.value;
  render();
});

elements.rarityFilter.addEventListener("change", (event) => {
  state.rarity = event.target.value;
  render();
});

elements.minPrice.addEventListener("input", (event) => {
  state.minPrice = event.target.value === "" ? Number.NEGATIVE_INFINITY : Number(event.target.value);
  render();
});

elements.maxPrice.addEventListener("input", (event) => {
  state.maxPrice = event.target.value === "" ? Number.POSITIVE_INFINITY : Number(event.target.value);
  render();
});

elements.sectionFilter.addEventListener("change", (event) => {
  state.section = event.target.value;
  render();
});

load();
