const API_URL = "/api/files";

const tableBody = document.querySelector("[data-table-body]");
const emptyState = document.querySelector("[data-empty]");
const statusEl = document.querySelector("[data-status]");
const countEl = document.querySelector("[data-count]");
const updatedEl = document.querySelector("[data-updated]");
const refreshBtn = document.querySelector("[data-refresh]");
const searchInput = document.querySelector("[data-search]");
const hostEl = document.querySelector("[data-host]");

if (hostEl) {
    hostEl.textContent = window.location.origin;
}

let files = [];
let refreshTimer;

async function loadFiles() {
    setLoading(true);
    setStatus("最新の情報を取得しています...");
    try {
        const response = await fetch(API_URL, { cache: "no-store" });
        if (!response.ok) {
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
    const filtered = keyword
        ? files.filter((file) => file.filename.toLowerCase().includes(keyword))
        : files;

    countEl.textContent = files.length;
    const hasFiles = files.length > 0;
    if (emptyState) {
        emptyState.hidden = hasFiles;
    }

    if (!filtered.length) {
        const message = hasFiles
            ? "検索条件に一致するファイルがありません"
            : "アップロードされたファイルはまだありません";
        tableBody.innerHTML = `<tr><td colspan="5" class="placeholder">${message}</td></tr>`;
        return;
    }

    tableBody.innerHTML = "";
    for (const file of filtered) {
        tableBody.appendChild(createRow(file));
    }
}

function createRow(file) {
    const tr = document.createElement("tr");

    const fileCell = document.createElement("td");
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
    sizeCell.textContent = file.size_readable || `${file.size} B`;

    const uploadedCell = document.createElement("td");
    uploadedCell.textContent = file.uploaded_at || "--";

    const typeCell = document.createElement("td");
    typeCell.textContent = file.file_type || "-";

    const actionCell = document.createElement("td");
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

refreshBtn?.addEventListener("click", () => loadFiles());
searchInput?.addEventListener("input", () => renderFiles());
tableBody?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.open) {
        window.open(target.dataset.open, "_blank", "noopener");
    }
});

loadFiles();
