/**
 * Dashboard solveur local — suivi du poids de la base vers 5 Go + métriques de calcul.
 */

const POLL_MS = 2000;
const PROCESS_POLL_MS = 3000;

const el = (id) => document.getElementById(id);

const dbSizeEl = el("db-size");
const dbLimitEl = el("db-limit");
const dbBarEl = el("db-bar");
const dbFillLabelEl = el("db-fill-label");
const dbEtaEl = el("db-eta");
const estTotalEl = el("est-total");
const statDurationEl = el("stat-duration");
const statSolvedEl = el("stat-solved");
const statRateEl = el("stat-rate");
const statEmptyEl = el("stat-empty");
const statEtaEl = el("stat-eta");
const statQueueEl = el("stat-queue");
const statPhaseEl = el("stat-phase");
const statMaxEmptyCurrentEl = el("stat-max-empty-current");
const maxEmptyStepsEl = el("max-empty-steps");
const statUpdatedEl = el("stat-updated");
const statusBadgeEl = el("status-badge");
const recentGridEl = el("recent-grid");
const messageEl = el("message");
const processBadgeEl = el("process-badge");
const btnStartSolverEl = el("btn-start-solver");
const btnStopSolverEl = el("btn-stop-solver");
const controlsMessageEl = el("controls-message");

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error(`Réponse non-JSON (HTTP ${response.status})`);
  }
  const data = await response.json();
  return { response, data };
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (d > 0) return `${d} j ${h} h`;
  if (h > 0) return `${h} h ${m} min`;
  if (m > 0) return `${m} min ${sec} s`;
  return `${sec} s`;
}

function formatEta(seconds) {
  if (seconds == null) return "—";
  return `~${formatDuration(seconds)}`;
}

function formatGo(bytes) {
  if (bytes == null) return "—";
  return `${(bytes / 1e9).toFixed(2).replace(".", ",")} Go`;
}

function formatCount(n) {
  if (n == null) return "—";
  if (n >= 1e6) return `≈ ${(n / 1e6).toFixed(1).replace(".", ",")} M`;
  if (n >= 1e3) return `≈ ${(n / 1e3).toFixed(0)} k`;
  return n.toLocaleString("fr-FR");
}

function formatEmptyRange(min, max) {
  if (min == null && max == null) return "—";
  if (max == null || min === max) return `${min} cases`;
  return `${min} → ${max} cases`;
}

function elapsedSince(iso) {
  if (!iso) return null;
  const start = new Date(iso).getTime();
  if (Number.isNaN(start)) return null;
  return (Date.now() - start) / 1000;
}

function statusLabel(status) {
  const map = {
    en_cours: { text: "En cours", cls: "status-running" },
    calcul_long: { text: "Calcul long", cls: "status-running" },
    rechargement: { text: "Rechargement", cls: "status-running" },
    en_veille: { text: "En veille (niveau complet)", cls: "status-paused" },
    pause: { text: "Pause", cls: "status-paused" },
    termine: { text: "Terminé", cls: "status-done" },
  };
  return map[status] || { text: status || "—", cls: "status-paused" };
}

function phaseLabel(phase, phaseLabelFromApi) {
  if (phaseLabelFromApi) return phaseLabelFromApi;
  const map = {
    endgame: "Fin de partie",
    midgame: "Milieu de partie",
    opening: "Ouverture",
    complet: "Complet",
    full: "Exploration",
  };
  return map[phase] || phase || "—";
}

function resultLabel(result) {
  const map = { W: "Victoire", L: "Défaite", D: "Nul" };
  return map[result] || result;
}

function renderMiniBoard(container, pos) {
  const board = pos.board;
  if (!board?.length) {
    container.textContent = "Plateau indisponible";
    return;
  }
  const grid = document.createElement("div");
  grid.className = "mini-board";
  grid.setAttribute("aria-label", `Position ${pos.hash?.slice(0, 8)}`);

  const best = pos.best_move;
  const last = pos.last_move;

  for (let row = 0; row < board.length; row++) {
    for (let col = 0; col < board[row].length; col++) {
      const cell = document.createElement("div");
      cell.className = "mini-cell";
      const player = board[row][col];
      if (player === 1) cell.classList.add("player-1");
      if (player === 2) cell.classList.add("player-2");
      if (best && best.row === row && best.col === col) cell.classList.add("best-move");
      if (last && last.row === row && last.col === col) cell.classList.add("last-move");
      grid.appendChild(cell);
    }
  }
  container.appendChild(grid);
}

function renderRecent(positions) {
  recentGridEl.innerHTML = "";
  if (!positions?.length) {
    recentGridEl.innerHTML = '<p class="muted">Aucune position récente pour l\'instant.</p>';
    return;
  }
  for (const pos of positions) {
    const card = document.createElement("article");
    card.className = "position-card";

    const boardWrap = document.createElement("div");
    boardWrap.className = "position-board-wrap";
    renderMiniBoard(boardWrap, pos);

    const meta = document.createElement("div");
    meta.className = "position-meta";
    const wr = (pos.win_rate * 100).toFixed(1);
    meta.innerHTML = `
      <span class="result-badge result-${pos.result}">${pos.result} — ${resultLabel(pos.result)}</span>
      <span class="win-rate">${wr}%</span>
      <span class="hash" title="${pos.hash}">${(pos.hash || "").slice(0, 10)}…</span>
    `;

    card.appendChild(boardWrap);
    card.appendChild(meta);
    recentGridEl.appendChild(card);
  }
}

const DEFAULT_MAX_EMPTY_LEVELS = [12, 20, 30, 40, 49];

function maxEmptyStepStatus(index, levelIdx) {
  if (index < levelIdx) return "done";
  if (index === levelIdx) return "active";
  return "pending";
}

function renderMaxEmptySteps(data) {
  const levels = data.max_empty_levels?.length ? data.max_empty_levels : DEFAULT_MAX_EMPTY_LEVELS;
  const levelIdx = Number(data.max_empty_level_idx ?? 0);
  const current = data.max_empty ?? levels[levelIdx] ?? levels[0];

  statMaxEmptyCurrentEl.textContent = String(current);
  maxEmptyStepsEl.innerHTML = "";

  levels.forEach((value, index) => {
    const status = maxEmptyStepStatus(index, levelIdx);
    const step = document.createElement("div");
    step.className = `max-empty-step ${status}`;
    step.setAttribute("role", "listitem");

    const box = document.createElement("div");
    box.className = "max-empty-step-box";
    box.textContent = String(value);

    const label = document.createElement("span");
    label.className = "max-empty-step-label";
    label.textContent = index === 0 ? "endgame" : `niv. ${index + 1}`;

    step.appendChild(box);
    step.appendChild(label);
    maxEmptyStepsEl.appendChild(step);
  });
}

function updateUI(data) {
  // Poids de la base → 5 Go
  const fill = Math.min(100, Math.max(0, data.db_fill_percent ?? 0));
  dbSizeEl.textContent = formatGo(data.db_size_bytes);
  dbLimitEl.textContent = `${Math.round((data.db_size_limit_bytes ?? 0) / 1073741824)} Go`;
  dbBarEl.style.width = `${fill}%`;
  dbBarEl.setAttribute("aria-valuenow", String(fill));
  dbFillLabelEl.textContent = `${fill.toFixed(1).replace(".", ",")} %`;
  dbEtaEl.textContent = formatEta(data.db_eta_seconds);
  estTotalEl.textContent = formatCount(data.est_total_positions);
  statDurationEl.textContent = formatDuration(elapsedSince(data.started_at));

  // Métriques
  statSolvedEl.textContent = (data.total_positions_solved ?? 0).toLocaleString("fr-FR");
  statRateEl.textContent =
    data.positions_per_second > 0
      ? `${data.positions_per_second.toLocaleString("fr-FR")} /s`
      : "—";
  statEmptyEl.textContent = formatEmptyRange(data.current_empty_min, data.current_empty_max);
  statEtaEl.textContent = formatEta(data.db_eta_seconds);
  statQueueEl.textContent = `${(data.total_queued ?? 0).toLocaleString("fr-FR")} / ${(
    data.in_progress ?? 0
  ).toLocaleString("fr-FR")}`;
  statPhaseEl.textContent = phaseLabel(data.current_phase, data.phase_label);

  const badge = statusLabel(data.status);
  statusBadgeEl.textContent = badge.text;
  statusBadgeEl.className = `status-badge ${badge.cls}`;

  renderMaxEmptySteps(data);
  statUpdatedEl.textContent = data.last_update
    ? new Date(data.last_update).toLocaleString("fr-FR")
    : "—";

  renderRecent(data.recent_positions);
  messageEl.textContent = data.db_available
    ? ""
    : "Base tablebase absente — initialisez-la puis lancez le worker Rust.";
}

async function poll() {
  try {
    const { response, data } = await fetchJson("/api/solver/status");
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    updateUI(data);
  } catch (error) {
    messageEl.textContent = `Impossible de joindre l'API locale : ${error.message}`;
  }
}

function renderProcessStatus(data) {
  const running = Boolean(data?.running);
  processBadgeEl.textContent = running ? "Solveur actif" : "Solveur arrêté";
  processBadgeEl.className = `status-badge ${running ? "status-running" : "status-paused"}`;
  btnStartSolverEl.disabled = running;
  btnStopSolverEl.disabled = !running;
}

function setControlsMessage(text, isError = false) {
  controlsMessageEl.textContent = text || "";
  controlsMessageEl.classList.toggle("message", Boolean(isError));
  controlsMessageEl.classList.toggle("muted", !isError);
}

async function pollProcessStatus() {
  try {
    const { response, data } = await fetchJson("/api/local/process-status");
    if (response.ok && data.success) {
      renderProcessStatus(data);
      return;
    }
    throw new Error(data.error || `HTTP ${response.status}`);
  } catch (error) {
    processBadgeEl.textContent = "État indisponible";
    processBadgeEl.className = "status-badge status-paused";
    setControlsMessage(error.message, true);
  }
}

async function postLocalAction(url, successFallback) {
  setControlsMessage("");
  btnStartSolverEl.disabled = true;
  btnStopSolverEl.disabled = true;
  try {
    const { response, data } = await fetchJson(url, { method: "POST" });
    if (!response.ok || !data.success) throw new Error(data.error || `HTTP ${response.status}`);
    setControlsMessage(data.message || successFallback);
  } catch (error) {
    setControlsMessage(error.message, true);
  } finally {
    // Convergence rapide : l'arrêt du moteur peut prendre ~1 s, on rafraîchit l'état plusieurs fois.
    for (let i = 0; i < 8; i++) {
      await new Promise((r) => setTimeout(r, 400));
      await pollProcessStatus();
    }
  }
}

btnStartSolverEl.addEventListener("click", () => {
  postLocalAction("/api/local/start-solver", "Solveur démarré.");
});

btnStopSolverEl.addEventListener("click", () => {
  postLocalAction("/api/local/stop-solver", "Solveur mis en pause.");
});

pollProcessStatus();
setInterval(pollProcessStatus, PROCESS_POLL_MS);
poll();
setInterval(poll, POLL_MS);
