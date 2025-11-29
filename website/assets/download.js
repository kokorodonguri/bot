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

  const formatDuration = (seconds) => {
    if (!Number.isFinite(seconds) || seconds < 0) return "-";
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60)
      .toString()
      .padStart(2, "0");
    return `${mins}:${secs}`;
  };

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
      const container = document.createElement("div");
      container.className = "audio-preview-card";

      const headline = document.createElement("div");
      headline.className = "audio-preview-headline";
      const icon = document.createElement("span");
      icon.className = "audio-preview-icon";
      icon.textContent = "🎧";
      const headlineText = document.createElement("div");
      headlineText.className = "audio-preview-headline-text";
      const label = document.createElement("div");
      label.className = "audio-preview-label";
      label.textContent = "音声プレビュー";
      const title = document.createElement("div");
      title.className = "audio-preview-title";
      title.textContent = data.filename;
      headlineText.appendChild(label);
      headlineText.appendChild(title);
      headline.appendChild(icon);
      headline.appendChild(headlineText);
      container.appendChild(headline);

      const meta = document.createElement("div");
      meta.className = "audio-preview-meta";
      const infoParts = [];
      if (data.mime_type) infoParts.push(data.mime_type);
      if (data.size_readable) infoParts.push(data.size_readable);
      meta.textContent = infoParts.join(" ・ ") || "音声ファイル";
      container.appendChild(meta);

      const audio = document.createElement("audio");
      audio.src = inlineUrl;
      audio.controls = false;
      audio.className = "preview-audio";
      audio.preload = "metadata";
      container.appendChild(audio);

      const durationRow = document.createElement("div");
      durationRow.className = "audio-duration-row";
      const durationLabel = document.createElement("span");
      durationLabel.textContent = "再生時間";
      const durationValue = document.createElement("strong");
      durationValue.className = "audio-duration-value";
      durationValue.textContent = "計測中...";
      audio.addEventListener("loadedmetadata", () => {
        durationValue.textContent = formatDuration(audio.duration);
      });
      audio.addEventListener("emptied", () => {
        durationValue.textContent = "-";
      });
      durationRow.appendChild(durationLabel);
      durationRow.appendChild(durationValue);
      container.appendChild(durationRow);

      const controls = document.createElement("div");
      controls.className = "audio-controls";

      const playButton = document.createElement("button");
      playButton.type = "button";
      playButton.className = "audio-play-button";
      const updatePlayButton = () => {
        playButton.textContent = audio.paused ? "▶ 再生" : "⏸ 一時停止";
      };
      playButton.addEventListener("click", () => {
        if (audio.paused) {
          audio.play();
        } else {
          audio.pause();
        }
      });
      audio.addEventListener("play", updatePlayButton);
      audio.addEventListener("pause", updatePlayButton);
      audio.addEventListener("ended", updatePlayButton);
      controls.appendChild(playButton);

      const timeline = document.createElement("div");
      timeline.className = "audio-timeline";
      const progress = document.createElement("input");
      progress.type = "range";
      progress.className = "audio-progress";
      progress.min = "0";
      progress.step = "0.1";
      progress.value = "0";
      progress.disabled = true;
      progress.setAttribute("aria-label", "再生位置");
      const timeLabel = document.createElement("span");
      timeLabel.className = "audio-time-label";
      let durationText = "-";
      const updateTimeLabel = () => {
        timeLabel.textContent = `${formatDuration(audio.currentTime)} / ${durationText}`;
      };
      const updateProgressFill = () => {
        if (!Number.isFinite(audio.duration) || audio.duration <= 0) {
          progress.style.removeProperty("--progress");
          return;
        }
        const percentage = (audio.currentTime / audio.duration) * 100;
        progress.style.setProperty("--progress", `${Math.min(Math.max(percentage, 0), 100)}%`);
      };
      progress.addEventListener("input", () => {
        const newTime = Number(progress.value);
        if (Number.isFinite(newTime)) {
          audio.currentTime = newTime;
          updateProgressFill();
          updateTimeLabel();
        }
      });
      audio.addEventListener("timeupdate", () => {
        if (!progress.disabled) {
          progress.value = audio.currentTime;
          updateProgressFill();
        }
        updateTimeLabel();
      });
      audio.addEventListener("loadedmetadata", () => {
        durationValue.textContent = formatDuration(audio.duration);
        durationText = formatDuration(audio.duration);
        progress.max = audio.duration.toString();
        progress.disabled = false;
        updateTimeLabel();
        updateProgressFill();
      });
      audio.addEventListener("emptied", () => {
        durationValue.textContent = "-";
        durationText = "-";
        progress.disabled = true;
        progress.value = "0";
        progress.style.removeProperty("--progress");
        updateTimeLabel();
      });
      timeline.appendChild(progress);
      timeline.appendChild(timeLabel);
      controls.appendChild(timeline);
      updatePlayButton();
      updateTimeLabel();
      container.appendChild(controls);

      const speedControls = document.createElement("div");
      speedControls.className = "audio-speed-controls";
      const speedLabel = document.createElement("span");
      speedLabel.className = "audio-speed-label";
      speedLabel.textContent = "再生速度";
      speedControls.appendChild(speedLabel);
      const speedButtonsWrap = document.createElement("div");
      speedButtonsWrap.className = "audio-speed-buttons";
      const speeds = [0.75, 1, 1.25, 1.5];
      const buttons = speeds.map((rate) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "audio-speed-button";
        btn.textContent = `${rate}x`;
        if (rate === 1) btn.classList.add("active");
        btn.addEventListener("click", () => {
          audio.playbackRate = rate;
          buttons.forEach((b) => b.classList.toggle("active", b === btn));
        });
        speedButtonsWrap.appendChild(btn);
        return btn;
      });
      speedControls.appendChild(speedButtonsWrap);
      container.appendChild(speedControls);

      const tip = document.createElement("p");
      tip.className = "audio-preview-tip";
      tip.textContent = "再生が開始しない場合はダウンロードしてお試しください。";
      container.appendChild(tip);

      previewBody.appendChild(container);
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
