const API_BASE = "/api";
const cloudLayer = document.getElementById("cloudLayer");

if (cloudLayer) {
    const CLOUD_COUNT = 7;

    const randomizeCloud = (cloud) => {
        const scale = (0.6 + Math.random() * 0.9).toFixed(2);
        const top = 10 + Math.random() * 130;
        const left = -10 + Math.random() * 120;

        cloud.style.setProperty("--scale", scale);
        cloud.style.top = `${top}px`;
        cloud.style.left = `${left}%`;
        cloud.style.transform = `scale(${scale})`;
    };

    Array.from({ length: CLOUD_COUNT }).forEach(() => {
        const cloud = document.createElement("div");
        cloud.className = "cloud";
        randomizeCloud(cloud);
        cloudLayer.appendChild(cloud);
    });
}

const uploadArea = document.getElementById("uploadArea");
const fileInput = document.getElementById("fileInput");
const selectButton = document.getElementById("selectButton");
const openBatchButton = document.getElementById("openBatchButton");
const downloadAllButton =
    document.getElementById("downloadAllButton");
const errorContainer = document.getElementById("errorContainer");
const successContainer =
    document.getElementById("successContainer");
const queueList = document.getElementById("queueList");
const queueEmpty = document.getElementById("queueEmpty");
const queueCount = document.getElementById("queueCount");
const shareLinks = document.getElementById("shareLinks");
const shareHint = document.getElementById("shareHint");
const copyCountBadge = document.getElementById("copyCountBadge");
const zipCountBadge = document.getElementById("zipCountBadge");
const previewClose = document.getElementById("previewClose");

const uploadQueue = [];
const STATE_CLASSES = [
    "pending",
    "uploading",
    "success",
    "error",
    "canceled",
];
let currentUploadItem = null;

const formatBytes = (bytes) => {
    if (!bytes || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const exponent = Math.min(
        Math.floor(Math.log(bytes) / Math.log(1024)),
        units.length - 1,
    );
    const value = bytes / 1024 ** exponent;
    const rounded = value.toFixed(
        value >= 10 || exponent === 0 ? 0 : 1,
    );
    return `${rounded} ${units[exponent]}`;
};

const readyLinks = () =>
    uploadQueue
        .filter(
            (item) =>
                item.state === "success" &&
                item.linkAnchor.textContent.trim() &&
                item.linkAnchor.href &&
                !item.linkAnchor.href.endsWith("#"),
        )
        .map((item) => item.linkAnchor.href.trim())
        .filter(Boolean);

const readyTokens = () => {
    const seen = new Set();
    return uploadQueue
        .filter((item) => item.state === "success" && item.token)
        .map((item) => item.token)
        .filter((token) => {
            if (seen.has(token)) return false;
            seen.add(token);
            return true;
        });
};

const renderShareArea = () => {
    if (!shareLinks || !shareHint) return;
    shareLinks.innerHTML = "";
    const links = readyLinks();
    const tokens = readyTokens();

    if (openBatchButton) {
        openBatchButton.disabled = tokens.length === 0;
        openBatchButton.title = tokens.length
            ? "まとめダウンロードページを開く"
            : "アップロード完了後に利用できます";
    }
    if (copyCountBadge) {
        copyCountBadge.textContent = tokens.length.toString();
    }
    if (downloadAllButton) {
        downloadAllButton.disabled = tokens.length === 0;
        downloadAllButton.title = tokens.length
            ? "アップロード済みのファイルをまとめてダウンロード"
            : "アップロード完了後に利用できます";
    }
    if (zipCountBadge) {
        zipCountBadge.textContent = tokens.length.toString();
    }

    if (!links.length) {
        shareHint.textContent =
            "アップロード完了後にここへリンクが並びます";
        return;
    }

    shareHint.textContent = `${links.length}件のリンクをまとめて確認 / ZIPダウンロードできます`;
    links.forEach((url) => {
        const row = document.createElement("div");
        row.className = "share-link";
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.target = "_blank";
        anchor.rel = "noopener";
        anchor.textContent = url;
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "download-button";
        btn.textContent = "コピー";
        btn.dataset.url = url;
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            copyUrlToClipboard(btn);
        });
        row.append(anchor, btn);
        shareLinks.appendChild(row);
    });
};

renderShareArea();

const updateQueueMeta = () => {
    const hasItem =
        queueList && queueList.querySelector(".queue-item");
    if (queueEmpty) {
        queueEmpty.style.display = hasItem ? "none" : "block";
    }
    if (queueCount) {
        const total = queueList
            ? Array.from(
                  queueList.querySelectorAll(".queue-item"),
              ).filter((el) => !el.classList.contains("canceled"))
                  .length
            : 0;
        queueCount.textContent = `${total}件`;
    }
    renderShareArea();
};

const setState = (item, state, text) => {
    STATE_CLASSES.forEach((cls) =>
        item.element.classList.remove(cls),
    );
    item.element.classList.add(state);
    item.state = state;
    if (text) {
        item.statusText.textContent = text;
    }
    item.cancelButton.disabled = [
        "success",
        "error",
        "canceled",
    ].includes(state);
};

const createQueueItem = (file) => {
    const container = document.createElement("div");
    container.className = "queue-item pending";

    const row = document.createElement("div");
    row.className = "queue-row";

    const meta = document.createElement("div");
    meta.className = "queue-meta";

    const name = document.createElement("div");
    name.className = "file-name";
    name.textContent = file.name;

    const size = document.createElement("div");
    size.className = "file-size";
    size.textContent = formatBytes(file.size);

    meta.appendChild(name);
    meta.appendChild(size);

    const actions = document.createElement("div");
    actions.className = "queue-actions";

    const previewBtn = document.createElement("button");
    previewBtn.type = "button";
    previewBtn.className = "download-button";
    previewBtn.textContent = "プレビュー";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "cancel-button";
    cancelBtn.textContent = "キャンセル";

    actions.appendChild(previewBtn);
    actions.appendChild(cancelBtn);

    row.appendChild(meta);
    row.appendChild(actions);

    const progressBar = document.createElement("div");
    progressBar.className = "progress-bar";
    const progressFill = document.createElement("div");
    progressFill.className = "progress-fill";
    progressBar.appendChild(progressFill);

    const statusRow = document.createElement("div");
    statusRow.className = "queue-row";
    const statusText = document.createElement("div");
    statusText.className = "file-status progress-text";
    statusText.textContent = "待機中";
    statusRow.appendChild(statusText);

    const linkBox = document.createElement("div");
    linkBox.className = "download-url queue-link-box";
    const linkAnchor = document.createElement("a");
    linkAnchor.href = "#";
    linkAnchor.target = "_blank";
    linkAnchor.rel = "noopener";
    linkAnchor.textContent = "";
    linkAnchor.className = "share-link-anchor";
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "download-button";
    copyButton.textContent = "コピー";
    copyButton.addEventListener("click", (e) => {
        e.stopPropagation();
        copyUrlToClipboard(copyButton);
    });
    linkAnchor.addEventListener("click", (e) => {
        e.stopPropagation();
    });
    linkBox.appendChild(linkAnchor);
    linkBox.appendChild(copyButton);

    const item = {
        file,
        element: container,
        progressFill,
        statusText,
        linkBox,
        linkAnchor,
        copyButton,
        token: null,
        cancelButton: cancelBtn,
        state: "pending",
        xhr: null,
    };

    previewBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        showPreview(file);
    });

    cancelBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        cancelUpload(item);
    });

    container.appendChild(row);
    container.appendChild(progressBar);
    container.appendChild(statusRow);
    container.appendChild(linkBox);

    return item;
};

const startNextUpload = () => {
    if (currentUploadItem) return;
    const next = uploadQueue.find(
        (entry) => entry.state === "pending",
    );
    if (!next) return;
    uploadFile(next);
};

const cancelUpload = (item) => {
    if (["success", "error", "canceled"].includes(item.state)) {
        return;
    }
    setState(item, "canceled", "アップロードをキャンセルしました");
    if (item === currentUploadItem && item.xhr) {
        item.xhr.abort();
        item.xhr = null;
        currentUploadItem = null;
        startNextUpload();
        return;
    }
    updateQueueMeta();
    startNextUpload();
};

const uploadFile = (item) => {
    const formData = new FormData();
    formData.append("file", item.file);

    item.progressFill.style.width = "0%";
    item.linkBox.style.display = "none";
    item.linkAnchor.textContent = "";
    item.linkAnchor.href = "#";
    item.copyButton.dataset.url = "";

    setState(item, "uploading", "アップロード中...");
    currentUploadItem = item;

    const xhr = new XMLHttpRequest();
    item.xhr = xhr;

    xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            item.progressFill.style.width = `${percent}%`;
            item.statusText.textContent = `アップロード中... ${percent}%`;
        }
    });

    xhr.addEventListener("load", () => {
        let response = {};
        try {
            response = JSON.parse(xhr.responseText || "{}");
        } catch (e) {
            response = {};
        }
        if (xhr.status === 200 && response.url) {
            item.progressFill.style.width = "100%";
            setState(item, "success", "アップロード完了");
            item.linkAnchor.textContent = response.url;
            item.linkAnchor.href = response.url;
            item.copyButton.dataset.url = response.url;
            item.token = response.token;
            showSuccess(
                `「${item.file.name}」をアップロードしました`,
            );
        } else {
            const message =
                response.error || `アップロード失敗: ${xhr.status}`;
            setState(item, "error", message);
            showError(message);
        }
    });

    xhr.addEventListener("error", () => {
        setState(item, "error", "ネットワークエラーが発生しました");
        showError("ネットワークエラーが発生しました");
    });

    xhr.addEventListener("abort", () => {
        setState(
            item,
            "canceled",
            "アップロードをキャンセルしました",
        );
    });

    xhr.addEventListener("loadend", () => {
        if (item === currentUploadItem) {
            currentUploadItem = null;
        }
        item.xhr = null;
        updateQueueMeta();
        startNextUpload();
    });

    xhr.open("POST", API_BASE + "/upload");
    xhr.send(formData);
};

const addFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    files.forEach((file, index) => {
        const item = createQueueItem(file);
        uploadQueue.push(item);
        queueList.appendChild(item.element);
        if (files.length === 1 && index === 0) {
            showPreview(file);
        }
    });
    updateQueueMeta();
    startNextUpload();
    fileInput.value = "";
};

// Event listeners for file selection
selectButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () =>
    addFiles(fileInput.files),
);

openBatchButton?.addEventListener("click", () => {
    const tokens = readyTokens();
    if (!tokens.length) {
        showError("まとめてダウンロードできるファイルがありません");
        return;
    }
    const params = new URLSearchParams();
    params.set("tokens", tokens.join(","));
    const url = `${window.location.origin}/batch?${params.toString()}`;
    window.open(url, "_blank", "noopener");
    showSuccess("まとめページを開きます");
});

downloadAllButton?.addEventListener("click", async () => {
    const tokens = readyTokens();
    if (!tokens.length) {
        showError("まとめてダウンロードできるファイルがありません");
        return;
    }
    downloadAllButton.disabled = true;
    try {
        const response = await fetch(API_BASE + "/download/zip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tokens }),
        });
        if (!response.ok) {
            let message = "ZIPの作成に失敗しました";
            try {
                const data = await response.json();
                message = data.error || message;
            } catch (e) {
                const text = await response.text();
                if (text) message = text;
            }
            showError(message);
            return;
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download =
            tokens.length === 1
                ? "download.zip"
                : `download-${tokens.length}.zip`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showSuccess("ZIP をダウンロードしました");
    } catch (err) {
        showError("ZIPのダウンロード中にエラーが発生しました");
    } finally {
        downloadAllButton.disabled = false;
    }
});

// Drag and drop events
uploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadArea.classList.add("dragover");
});

uploadArea.addEventListener("dragleave", () => {
    uploadArea.classList.remove("dragover");
});

uploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadArea.classList.remove("dragover");
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        addFiles(files);
    }
});

function showError(message) {
    errorContainer.innerHTML = `<div class="error-message">${message}</div>`;
    setTimeout(() => {
        errorContainer.innerHTML = "";
    }, 5000);
}

function showSuccess(message) {
    successContainer.innerHTML = `<div class="success-message">${message}</div>`;
    setTimeout(() => {
        successContainer.innerHTML = "";
    }, 5000);
}

function markCopied(button) {
    const originalText = button.textContent;
    button.textContent = "コピー済み";
    button.classList.add("is-copied");
    setTimeout(() => {
        button.textContent = originalText;
        button.classList.remove("is-copied");
    }, 2000);
}

function copyUrlToClipboard(button) {
    const url =
        button.dataset.url ||
        button.previousElementSibling.textContent;
    if (!url) return;

    // Try modern Clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard
            .writeText(url)
            .then(() => {
                markCopied(button);
                showSuccess("リンクをコピーしました");
            })
            .catch(() => {
                // Fallback to legacy execCommand method
                legacyCopy(url, button);
            });
    } else {
        legacyCopy(url, button);
    }
}

function legacyCopy(text, button) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
        const ok = document.execCommand("copy");
        if (ok) {
            markCopied(button);
            showSuccess("リンクをコピーしました");
        } else {
            alert("コピーに失敗しました");
        }
    } catch (e) {
        alert("コピーに失敗しました");
    }
    document.body.removeChild(ta);
}

function closePreview() {
    document.getElementById("previewContainer").style.display = "none";
}

previewClose?.addEventListener("click", closePreview);

function showPreview(file) {
    const previewContainer =
        document.getElementById("previewContainer");
    const previewBody = document.getElementById("previewBody");
    const fileType = file.type;
    const fileName = file.name;

    previewBody.innerHTML = "";

    // Image preview
    if (fileType.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = document.createElement("img");
            img.src = e.target.result;
            img.className = "preview-image";
            previewBody.appendChild(img);
        };
        reader.readAsDataURL(file);
        previewContainer.style.display = "block";
        return;
    }

    // Video preview (MP4, WebM, Ogg)
    if (
        fileType.startsWith("video/") ||
        ["mp4", "webm", "ogv"].some((ext) =>
            fileName.toLowerCase().endsWith(ext),
        )
    ) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const video = document.createElement("video");
            video.src = e.target.result;
            video.className = "preview-video";
            video.controls = true;
            previewBody.appendChild(video);
        };
        reader.readAsDataURL(file);
        previewContainer.style.display = "block";
        return;
    }

    // Audio preview (MP3, WAV, OGG, etc.)
    if (
        fileType.startsWith("audio/") ||
        ["mp3", "wav", "ogg", "m4a"].some((ext) =>
            fileName.toLowerCase().endsWith(ext),
        )
    ) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const audio = document.createElement("audio");
            audio.src = e.target.result;
            audio.className = "preview-audio";
            audio.controls = true;

            const playButton = document.createElement("button");
            playButton.type = "button";
            playButton.className = "preview-play-button";
            playButton.textContent = "▶ 再生";
            playButton.addEventListener("click", () => {
                if (audio.paused) {
                    audio.play();
                    playButton.textContent = "⏸ 停止";
                } else {
                    audio.pause();
                    playButton.textContent = "▶ 再生";
                }
            });
            audio.addEventListener("ended", () => {
                playButton.textContent = "▶ 再生";
            });

            previewBody.appendChild(audio);
            previewBody.appendChild(playButton);
        };
        reader.readAsDataURL(file);
        previewContainer.style.display = "block";
        return;
    }

    // Text preview
    if (
        fileType.startsWith("text/") ||
        fileType === "application/json"
    ) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const pre = document.createElement("div");
            pre.className = "preview-text";
            pre.textContent = e.target.result.substring(0, 5000);
            if (e.target.result.length > 5000) {
                pre.textContent +=
                    "\n\n... (残り " +
                    (e.target.result.length - 5000) +
                    " 文字は省略されています)";
            }
            previewBody.appendChild(pre);
        };
        reader.readAsText(file);
        previewContainer.style.display = "block";
        return;
    }

    // PDF preview (embed)
    if (fileType === "application/pdf") {
        const reader = new FileReader();
        reader.onload = (e) => {
            const embed = document.createElement("iframe");
            embed.src = e.target.result;
            embed.style.width = "100%";
            embed.style.height = "300px";
            embed.style.border = "none";
            previewBody.appendChild(embed);
        };
        reader.readAsDataURL(file);
        previewContainer.style.display = "block";
        return;
    }

    // No preview available
    const notAvailable = document.createElement("div");
    notAvailable.className = "preview-unavailable";
    notAvailable.textContent = `このファイル形式 (${fileType || "unknown"}) はプレビューできません`;
    previewBody.appendChild(notAvailable);
    previewContainer.style.display = "block";
}

// IP retrieval removed (no IP display)
