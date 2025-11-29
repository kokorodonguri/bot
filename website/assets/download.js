(() => {
  const qs = (id) => document.getElementById(id);
  const fileView = qs("fileView");
  const loadingView = qs("loadingView");
  const errorView = qs("errorView");
  const previewSection = qs("previewSection");
  const previewBody = qs("previewBody");
  const previewNote = qs("previewNote");
  const fileName = qs("fileName");
  const fileSize = qs("fileSize");
  const fileUploaded = qs("fileUploaded");
  const fileMime = qs("fileMime");
  const downloadBtn = qs("downloadBtn");
  const copyBtn = qs("copyBtn");

  const getToken = () => {
    if (window.__FILE_TOKEN__) return window.__FILE_TOKEN__;
    const attr = document.body.getAttribute("data-token");
    if (attr) return attr;
    const segments = window.location.pathname.split("/").filter(Boolean);
    const idx = segments.indexOf("files");
    if (idx !== -1 && segments[idx + 1]) return segments[idx + 1];
    return null;
  };

  const showError = (message) => {
    loadingView.hidden = true;
    fileView.hidden = true;
    errorView.hidden = false;
    errorView.textContent = message;
  };

  const renderPreview = (data) => {
    previewBody.innerHTML = "";
    previewNote.hidden = true;
    const preview = data.preview || { kind: "none" };
    previewSection.hidden = false;

    const inlineUrl = data.inline_url;

    if (preview.kind === "image") {
      const img = document.createElement("img");
      img.src = inlineUrl;
      img.alt = data.filename;
      img.loading = "lazy";
      img.className = "preview-media";
      previewBody.appendChild(img);
      return;
    }

    if (preview.kind === "video") {
      const video = document.createElement("video");
      video.src = inlineUrl;
      video.controls = true;
      video.className = "preview-media video";
      previewBody.appendChild(video);
      return;
    }

    if (preview.kind === "audio") {
      const audio = document.createElement("audio");
      audio.src = inlineUrl;
      audio.controls = true;
      audio.className = "preview-audio";
      previewBody.appendChild(audio);
      return;
    }

    if (preview.kind === "pdf") {
      const frame = document.createElement("iframe");
      frame.src = inlineUrl;
      frame.className = "preview-frame";
      frame.title = data.filename;
      previewBody.appendChild(frame);
      return;
    }

    if (preview.kind === "text" && preview.snippet) {
      const pre = document.createElement("pre");
      pre.className = "preview-text-block";
      pre.textContent = preview.snippet;
      previewBody.appendChild(pre);
      if (preview.truncated) {
        previewNote.hidden = false;
        previewNote.textContent =
          "※ 省略されています。全文はファイルをダウンロードして確認してください。";
      }
      return;
    }

    const placeholder = document.createElement("p");
    placeholder.className = "preview-placeholder";
    placeholder.textContent =
      preview.message ||
      `このファイル形式 (${data.mime_type || "unknown"}) はプレビューに対応していません。`;
    previewBody.appendChild(placeholder);
  };

  const copyLink = async (url) => {
    try {
      await navigator.clipboard.writeText(url);
      const original = copyBtn.textContent;
      copyBtn.textContent = "コピーしました";
      copyBtn.disabled = true;
      setTimeout(() => {
        copyBtn.textContent = original;
        copyBtn.disabled = false;
      }, 2000);
    } catch (err) {
      alert(`コピーに失敗しました: ${err}`);
    }
  };

  const initClouds = () => {
    const layer = document.getElementById("cloudLayer");
    if (!layer) return;
    layer.innerHTML = "";
    const CLOUD_COUNT = 7;
    const randomize = (cloud) => {
      const scale = 0.6 + Math.random() * 0.9;
      const top = 10 + Math.random() * 130;
      const left = -10 + Math.random() * 120;
      cloud.style.top = `${top}px`;
      cloud.style.left = `${left}%`;
      cloud.style.transform = `scale(${scale.toFixed(2)})`;
    };
    Array.from({ length: CLOUD_COUNT }).forEach(() => {
      const cloud = document.createElement("div");
      cloud.className = "cloud";
      randomize(cloud);
      layer.appendChild(cloud);
    });
  };

  const load = async () => {
    const token = getToken();
    if (!token) {
      showError("トークンを特定できませんでした。URL を確認してください。");
      return;
    }

    try {
      const res = await fetch(`/api/file/${token}`);
      if (!res.ok) {
        const message =
          res.status === 404
            ? "ファイルが見つかりませんでした。"
            : `ファイル情報の取得に失敗しました (status ${res.status})`;
        showError(message);
        return;
      }
      const data = await res.json();

      document.title = `${data.filename} - ファイルダウンロード`;
      fileName.textContent = data.filename;
      fileSize.textContent = data.size_readable || `${data.size} bytes`;
      fileUploaded.textContent = data.uploaded_at || "-";
      fileMime.textContent = data.mime_type || "不明";
      downloadBtn.href = data.download_url;
      copyBtn.dataset.url = data.base_url;

      renderPreview(data);

      loadingView.hidden = true;
      errorView.hidden = true;
      fileView.hidden = false;

      copyBtn.addEventListener("click", () =>
        copyLink(copyBtn.dataset.url || data.base_url),
      );
    } catch (err) {
      showError(`ファイル情報の取得に失敗しました: ${err}`);
    }
  };

  const start = () => {
    initClouds();
    load();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
