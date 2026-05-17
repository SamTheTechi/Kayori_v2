const tokenInput = document.getElementById("token");
const statusNode = document.getElementById("status");
const moodNode = document.getElementById("mood");
const lifeNotesNode = document.getElementById("life-notes");
const historyNode = document.getElementById("history");
const logsNode = document.getElementById("logs");

let loading = false;

tokenInput.value = localStorage.getItem("kayori_dashboard_token") || "";

tokenInput.addEventListener("input", () => {
  localStorage.setItem("kayori_dashboard_token", tokenInput.value.trim());
  loadDashboard();
});

function setStatus(text) {
  statusNode.textContent = text;
}

function authHeaders() {
  const token = tokenInput.value.trim();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchJson(path) {
  const response = await fetch(path, { headers: authHeaders() });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) {}
    throw new Error(`${response.status} ${detail}`);
  }
  return response.json();
}

function renderMood(data) {
  const mood = data && data.mood ? data.mood : {};
  const entries = Object.entries(mood).sort(
    (a, b) => Number(b[1]) - Number(a[1]),
  );
  if (!entries.length) {
    moodNode.innerHTML = '<div class="empty">No mood data.</div>';
    return;
  }
  moodNode.innerHTML = `<div class="kv">${entries
    .map(
      ([key, value]) => `
    <div class="kv-row">
      <span>${escapeHtml(key)}</span>
      <span class="mono">${Number(value).toFixed(3)}</span>
    </div>
  `,
    )
    .join("")}</div>`;
}

function renderLifeNotes(data) {
  const notes = data && Array.isArray(data.life_notes) ? data.life_notes : [];
  if (!notes.length) {
    lifeNotesNode.innerHTML = '<div class="empty">No life notes.</div>';
    return;
  }
  lifeNotesNode.innerHTML = `<ul class="notes">${notes
    .slice()
    .reverse()
    .map(
      (note) => `
    <li>
      <div class="note-body">${escapeHtml(note.content || "")}</div>
      <div class="note-time muted mono">${escapeHtml(note.timestamp || "")}</div>
    </li>
  `,
    )
    .join("")}</ul>`;
}

function renderHistory(data) {
  const count = Number((data && data.count) || 0);
  const messages = ((data || {}).history || {}).messages || [];
  const preview = messages
    .slice(-3)
    .map(formatHistoryMessage)
    .filter(Boolean)
    .join("\n\n");
  setHtmlPreserveScroll(
    historyNode,
    `
    <div class="kv">
      <div class="kv-row"><span>Messages</span><span class="mono">${count}</span></div>
    </div>
    <div class="history-preview">${escapeHtml(preview || "No recent messages.")}</div>
  `,
    ".history-preview",
  );
}

function renderLogs(data) {
  const logs = data && Array.isArray(data.logs) ? data.logs : [];
  if (!logs.length) {
    logsNode.innerHTML = '<div class="empty">No logs.</div>';
    return;
  }
  setHtmlPreserveScroll(
    logsNode,
    logs
      .map(
        (item) => `
    <div class="log-item">
      <div class="log-meta">
        <span>${escapeHtml(item.timestamp || "")}</span>
        <span class="tag ${escapeHtml(item.level || "")}">${escapeHtml(item.level || "info")}</span>
        <span>${escapeHtml(item.logger || "")}</span>
      </div>
      <div>${escapeHtml(item.message || item.event || "")}</div>
    </div>
  `,
      )
      .join(""),
    ".log-list",
  );
}

function showPanelError(node, message) {
  node.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatHistoryMessage(item) {
  const type = item && item.type ? String(item.type) : "message";
  const data = item && item.data ? item.data : {};
  const content = formatMessageContent(data.content);
  if (!content) {
    return `[${type}]`;
  }
  return `[${type}] ${content}`;
}

function formatMessageContent(content) {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") {
          return part;
        }
        if (part && typeof part.text === "string") {
          return part.text;
        }
        return "";
      })
      .filter(Boolean)
      .join(" ");
  }
  return "";
}

function setHtmlPreserveScroll(node, html, selector) {
  if (node.innerHTML === html) {
    return;
  }

  const scrollNode = selector ? node.querySelector(selector) : node;
  const scrollTop = scrollNode ? scrollNode.scrollTop : 0;

  node.innerHTML = html;

  const nextScrollNode = selector ? node.querySelector(selector) : node;
  if (nextScrollNode) {
    nextScrollNode.scrollTop = scrollTop;
  }
}

async function loadPanels() {
  try {
    const [mood, lifeNotes, history] = await Promise.all([
      fetchJson("/api/metrics/mood"),
      fetchJson("/api/metrics/life-notes"),
      fetchJson("/api/metrics/history"),
    ]);
    renderMood(mood);
    renderLifeNotes(lifeNotes);
    renderHistory(history);
  } catch (error) {
    showPanelError(moodNode, error.message);
    showPanelError(lifeNotesNode, error.message);
    showPanelError(historyNode, error.message);
  }
}

async function loadDashboard() {
  if (loading) {
    return;
  }
  loading = true;

  try {
    const [logsData] = await Promise.all([fetchJson("/api/logs?limit=50")]);

    renderLogs(logsData);
    await loadPanels();
    setStatus("Live");
  } catch (error) {
    showPanelError(moodNode, error.message);
    showPanelError(lifeNotesNode, error.message);
    showPanelError(historyNode, error.message);
    showPanelError(logsNode, error.message);
    setStatus("Auth or fetch error");
  } finally {
    loading = false;
  }
}

loadDashboard();
setInterval(loadDashboard, 5000);
