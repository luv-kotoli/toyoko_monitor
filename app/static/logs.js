const elements = {
  logsStatus: document.querySelector("#logs-status"),
  refreshButton: document.querySelector("#refresh-logs-button"),
  logGrid: document.querySelector("#log-grid"),
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  void loadLogs();
  window.setInterval(() => {
    void loadLogs({ silent: true });
  }, 15000);
});

function bindEvents() {
  elements.refreshButton.addEventListener("click", () => {
    void loadLogs();
  });
}

async function loadLogs({ silent = false } = {}) {
  if (!silent) {
    setStatus("正在加载日志");
  }

  try {
    const response = await api("/api/logs?line_count=100");
    renderLogs(response.sections || []);
    setStatus(`已刷新 ${response.line_count} 行`);
  } catch (error) {
    console.error(error);
    setStatus(`日志加载失败: ${error.message}`);
  }
}

function renderLogs(sections) {
  if (sections.length === 0) {
    elements.logGrid.innerHTML = `
      <article class="log-card">
        <div class="log-card-head">
          <h3>日志</h3>
          <span class="muted">无数据</span>
        </div>
        <textarea class="log-box" readonly>暂无日志可显示。</textarea>
      </article>
    `;
    return;
  }

  elements.logGrid.innerHTML = sections
    .map(
      (section) => `
        <article class="log-card">
          <div class="log-card-head">
            <h3>${escapeHtml(section.label)}</h3>
            <span class="muted">${escapeHtml(section.file_name)} · 最后 100 行</span>
          </div>
          <textarea class="log-box" readonly data-log-key="${escapeHtml(section.key)}">${escapeHtml(section.content)}</textarea>
        </article>
      `,
    )
    .join("");

  document.querySelectorAll("[data-log-key]").forEach((textarea) => {
    textarea.scrollTop = textarea.scrollHeight;
  });
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  const payload = await response.json();
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : response.statusText;
    throw new Error(detail);
  }
  return payload;
}

function setStatus(text) {
  elements.logsStatus.textContent = text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
