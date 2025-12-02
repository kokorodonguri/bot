const API_URL = "/api/files";
const LOGIN_URL = "/login";

const tableBody = document.querySelector("[data-table-body]");
const emptyState = document.querySelector("[data-empty]");
const statusEl = document.querySelector("[data-status]");
const countEl = document.querySelector("[data-count]");
const updatedEl = document.querySelector("[data-updated]");
const refreshBtn = document.querySelector("[data-refresh]");
const searchInput = document.querySelector("[data-search]");
const hostEl = document.querySelector("[data-host]");
const timeFilterSelect = document.querySelector("[data-time-filter]");
const sortBtn = document.querySelector("[data-sort]");

if (hostEl) {
  hostEl.textContent = window.location.origin;
}

let files = [];
let refreshTimer;
let sortDesc = true;

function redirectToLogin() {
  const next = encodeURIComponent(
    window.location.pathname + window.location.search,
  );
  window.location.href = `${LOGIN_URL}?next=${next}`;
}

async function loadFiles() {
  setLoading(true);
  setStatus("最新の情報を取得しています...");
  try {
    const response = await fetch(API_URL, { cache: "no-store" });
    if (!response.ok) {
      if (response.status === 401) {
        redirectToLogin();
        return;
      }
      throw new Error(`status ${response.status}`);
    }
    const data = await response.json();
    files = Array.isArray(data) ? data : [];
    renderFiles();
    if (files.length) {
      updatedEl.textContent = files[0].uploaded_at || "--";
    } else {
      updatedEl.textContent = "--";
    }
    setStatus(`最終更新: ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    console.error(error);
    setStatus("ファイル一覧の取得に失敗しました", true);
  } finally {
    setLoading(false);
    scheduleNextRefresh();
  }
}

function renderFiles() {
  const keyword = (searchInput?.value || "").trim().toLowerCase();
  const filteredBySearch = keyword
    ? files.filter((file) => file.filename.toLowerCase().includes(keyword))
    : files;
  const filtered = filteredBySearch.filter((file) => includeByTime(file));

  const sorted = sortByDate(filtered);

  countEl.textContent = files.length;
  const hasFiles = files.length > 0;
  if (emptyState) {
    emptyState.hidden = hasFiles;
  }

  if (!sorted.length) {
    const message = hasFiles
      ? "検索条件に一致するファイルがありません"
      : "アップロードされたファイルはまだありません";
    tableBody.innerHTML = `<tr><td colspan="5" class="placeholder">${message}</td></tr>`;
    return;
  }

  tableBody.innerHTML = "";
  for (const file of sorted) {
    tableBody.appendChild(createRow(file));
  }
}

function createRow(file) {
  const tr = document.createElement("tr");

  const fileCell = document.createElement("td");
  fileCell.dataset.label = "ファイル名";
  const nameWrap = document.createElement("div");
  nameWrap.className = "file-name";
  const link = document.createElement("a");
  link.href = file.url;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = file.filename;
  const token = document.createElement("span");
  token.className = "file-token";
  token.textContent = `Token: ${file.token}`;
  nameWrap.append(link, token);
  fileCell.appendChild(nameWrap);

  const sizeCell = document.createElement("td");
  sizeCell.dataset.label = "サイズ";
  sizeCell.textContent = file.size_readable || `${file.size} B`;

  const uploadedCell = document.createElement("td");
  uploadedCell.dataset.label = "アップロード日時";
  uploadedCell.textContent = file.uploaded_at || "--";

  const typeCell = document.createElement("td");
  typeCell.dataset.label = "ファイルタイプ";
  typeCell.textContent = file.file_type || "-";

  const actionCell = document.createElement("td");
  actionCell.dataset.label = "操作";
  const actionWrap = document.createElement("div");
  actionWrap.className = "actions";
  const openBtn = document.createElement("button");
  openBtn.type = "button";
  openBtn.className = "btn-open";
  openBtn.dataset.open = file.url;
  openBtn.textContent = "開く";
  actionWrap.appendChild(openBtn);
  actionCell.appendChild(actionWrap);

  tr.append(fileCell, sizeCell, uploadedCell, typeCell, actionCell);
  return tr;
}

function setStatus(message, isError = false) {
  if (!statusEl) {
    return;
  }
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#dc2626" : "var(--subtle)";
}

function setLoading(isLoading) {
  if (!refreshBtn) {
    return;
  }
  refreshBtn.disabled = isLoading;
}

function scheduleNextRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => loadFiles(), 60000);
}

function includeByTime(file) {
  if (!timeFilterSelect) {
    return true;
  }
  const value = timeFilterSelect.value;
  if (value === "all") {
    return true;
  }
  const windowMap = {
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
    "30d": 30 * 24 * 60 * 60 * 1000,
  };
  const range = windowMap[value];
  if (!range) {
    return true;
  }
  const uploaded = parseUploadDate(file.uploaded_at);
  if (!uploaded) {
    return true;
  }
  return Date.now() - uploaded.getTime() <= range;
}

function parseUploadDate(value) {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return value;
  }
  if (typeof value === "number") {
    return new Date(value > 1e12 ? value : value * 1000);
  }
  const normalized = new Date(String(value));
  if (!Number.isNaN(normalized.getTime())) {
    return normalized;
  }
  const cleaned = String(value).trim().replace(/\//g, "-").replace(" ", "T");
  const isoLike = new Date(cleaned);
  if (!Number.isNaN(isoLike.getTime())) {
    return isoLike;
  }
  const match = String(value)
    .trim()
    .match(/^(\d{4})[\/\-](\d{2})[\/\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/);
  if (match) {
    const [, year, month, day, hour, minute, second] = match;
    return new Date(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
    );
  }
  return null;
}

function sortByDate(list) {
  return [...list].sort((a, b) => {
    const aDate = parseUploadDate(a.uploaded_at);
    const bDate = parseUploadDate(b.uploaded_at);
    const aTime = aDate ? aDate.getTime() : 0;
    const bTime = bDate ? bDate.getTime() : 0;
    return sortDesc ? bTime - aTime : aTime - bTime;
  });
}

function updateSortButton() {
  if (!sortBtn) {
    return;
  }
  sortBtn.textContent = sortDesc ? "新しい順" : "古い順";
}

refreshBtn?.addEventListener("click", () => loadFiles());
searchInput?.addEventListener("input", () => renderFiles());
timeFilterSelect?.addEventListener("change", () => renderFiles());
sortBtn?.addEventListener("click", () => {
  sortDesc = !sortDesc;
  updateSortButton();
  renderFiles();
});
tableBody?.addEventListener("click", (event) => {
  const target = event.target;
  if (target instanceof HTMLElement && target.dataset.open) {
    window.open(target.dataset.open, "_blank", "noopener");
  }
});

updateSortButton();
loadFiles();
