/**
 * Dashboard solveur local — endgame (5 Go) ou livre d'ouverture (2 Go).
 */

const POLL_MS = 2000;
const PROCESS_POLL_MS = 3000;

const el = (id) => document.getElementById(id);

const pageTitleEl = el("page-title");
const pageSubtitleEl = el("page-subtitle");
const controlsPanelEl = el("controls-panel");
const openingBannerEl = el("opening-book-banner");
const openingBookStatsEl = el("opening-book-stats");
const heroTitleEl = el("hero-title");
const heroEtaLabelEl = el("hero-eta-label");
const heroEstLabelEl = el("hero-est-label");
const dbSizeEl = el("db-size");
const dbLimitEl = el("db-limit");
const dbBarEl = el("db-bar");
const dbFillLabelEl = el("db-fill-label");
const dbEtaEl = el("db-eta");
const estTotalEl = el("est-total");
const statDurationEl = el("stat-duration");
const statSolvedLabelEl = el("stat-solved-label");
const statSolvedEl = el("stat-solved");
const statRateEl = el("stat-rate");
const statExtraLabelEl = el("stat-extra-label");
const statEmptyEl = el("stat-empty");
const statEtaLabelEl = el("stat-eta-label");
const statEtaEl = el("stat-eta");
const statQueueWrapEl = el("stat-queue-wrap");
const statQueueEl = el("stat-queue");
const statPhaseEl = el("stat-phase");
const statExactWrapEl = el("stat-exact-wrap");
const statExactEl = el("stat-exact");
const statEstimatedWrapEl = el("stat-estimated-wrap");
const statEstimatedEl = el("stat-estimated");
const statMaxEmptyCurrentEl = el("stat-max-empty-current");
const maxEmptyPanelEl = el("max-empty-panel");
const maxEmptyStepsEl = el("max-empty-steps");
const statUpdatedEl = el("stat-updated");
const statusBadgeEl = el("status-badge");
const recentTitleEl = el("recent-title");
const recentGridEl = el("recent-grid");
const messageEl = el("message");
const processBadgeEl = el("process-badge");
const btnStartSolverEl = el("btn-start-solver");
const btnStopSolverEl = el("btn-stop-solver");
const controlsMessageEl = el("controls-message");

let lastBuildMode = null;

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

function isOpeningBookMode(data) {
  return data.build_mode === "opening_book" || data.current_phase === "opening_book";
}

function statusLabel(status) {
  const map = {
    en_cours: { text: "En cours", cls: "status-running" },
    calcul_long: { text: "Calcul en cours…", cls: "status-running" },
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
    opening_book: "Livre d'ouverture",
    complet: "Complet",
    full: "Exploration",
  };
  return map[phase] || phase || "—";
}

function resultLabel(result) {
  const map = { W: "Victoire", L: "Défaite", D: "Nul" };
  return map[result] || result;
}

function applyLayoutMode(openingBook) {
  if (openingBook === lastBuildMode) return;
  lastBuildMode = openingBook;

  if (openingBook) {
    pageTitleEl.innerHTML = 'Livre d\'ouverture <span class="local-badge">local</span>';
    pageSubtitleEl.textContent =
      "Construction Rust parallèle — promotions exactes depuis la tablebase endgame";
    controlsPanelEl.classList.add("hidden");
    openingBannerEl.classList.remove("hidden");
    heroTitleEl.textContent = "Taille du livre d'ouverture";
    heroEtaLabelEl.textContent = "Temps estimé → 2 Go";
    heroEstLabelEl.textContent = "Entrées estimées (2 Go)";
    statSolvedLabelEl.textContent = "Entrées livre";
    statExtraLabelEl.textContent = "Ply max vague";
    statEtaLabelEl.textContent = "Temps restant (→ 2 Go)";
    statQueueWrapEl.classList.add("hidden");
    statExactWrapEl.classList.remove("hidden");
    statEstimatedWrapEl.classList.remove("hidden");
    maxEmptyPanelEl.classList.add("hidden");
    recentTitleEl.textContent = "Dernières ouvertures calculées";
    dbBarEl.classList.add("opening-bar");
  } else {
    pageTitleEl.innerHTML = 'Avancement solveur <span class="local-badge">local</span>';
    pageSubtitleEl.textContent = "Suivi en direct du worker Rust endgame — lecture de tablebase.db";
    controlsPanelEl.classList.remove("hidden");
    openingBannerEl.classList.add("hidden");
    heroTitleEl.textContent = "Poids de la base";
    heroEtaLabelEl.textContent = "Temps estimé → 5 Go";
    heroEstLabelEl.textContent = "Positions estimées au total";
    statSolvedLabelEl.textContent = "Positions calculées";
    statExtraLabelEl.textContent = "Cases vides en cours";
    statEtaLabelEl.textContent = "Temps restant (→ 5 Go)";
    statQueueWrapEl.classList.remove("hidden");
    statExactWrapEl.classList.add("hidden");
    statEstimatedWrapEl.classList.add("hidden");
    maxEmptyPanelEl.classList.remove("hidden");
    recentTitleEl.textContent = "Derniers coups calculés";
    dbBarEl.classList.remove("opening-bar");
  }
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
    recentGridEl.innerHTML = '<p class="muted">Aucune entrée récente pour l\'instant.</p>';
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
  const openingBook = isOpeningBookMode(data);
  applyLayoutMode(openingBook);

  const fill = Math.min(100, Math.max(0, data.db_fill_percent ?? data.progress_percent ?? 0));
  dbSizeEl.textContent = formatGo(data.db_size_bytes);
  dbLimitEl.textContent = `${Math.round((data.db_size_limit_bytes ?? 0) / 1073741824)} Go`;
  dbBarEl.style.width = `${fill}%`;
  dbBarEl.setAttribute("aria-valuenow", String(fill));
  dbFillLabelEl.textContent = `${fill.toFixed(1).replace(".", ",")} %`;
  dbEtaEl.textContent = formatEta(data.db_eta_seconds);
  estTotalEl.textContent = formatCount(data.est_total_positions ?? data.total_positions_target);
  statDurationEl.textContent = formatDuration(elapsedSince(data.started_at));

  statSolvedEl.textContent = (data.total_positions_solved ?? 0).toLocaleString("fr-FR");
  statRateEl.textContent =
    data.positions_per_second > 0
      ? `${data.positions_per_second.toLocaleString("fr-FR")} /s`
      : openingBook && data.solver_running
        ? "calcul…"
        : "—";

  if (openingBook) {
    statEmptyEl.textContent = data.max_empty != null ? `≤ ${data.max_empty} (vague)` : "—";
    const exact = data.opening_book_exact ?? 0;
    const estimated = data.opening_book_estimated ?? 0;
    statExactEl.textContent = exact.toLocaleString("fr-FR");
    statEstimatedEl.textContent = estimated.toLocaleString("fr-FR");
    if (openingBookStatsEl) {
      const total = data.total_positions_solved ?? exact + estimated;
      const pct = total > 0 ? ((100 * exact) / total).toFixed(1).replace(".", ",") : "0";
      openingBookStatsEl.textContent = `Exactes : ${exact.toLocaleString("fr-FR")} · Estimées : ${estimated.toLocaleString("fr-FR")} · ${pct} % exact (sur ${total.toLocaleString("fr-FR")} entrées)`;
    }
  } else {
    statEmptyEl.textContent = formatEmptyRange(data.current_empty_min, data.current_empty_max);
    statQueueEl.textContent = `${(data.total_queued ?? 0).toLocaleString("fr-FR")} / ${(
      data.in_progress ?? 0
    ).toLocaleString("fr-FR")}`;
    renderMaxEmptySteps(data);
  }

  statEtaEl.textContent = formatEta(data.db_eta_seconds);
  statPhaseEl.textContent = phaseLabel(data.current_phase, data.phase_label);

  const badge = statusLabel(data.status);
  statusBadgeEl.textContent = badge.text;
  statusBadgeEl.className = `status-badge ${badge.cls}`;

  statUpdatedEl.textContent = data.last_update
    ? new Date(data.last_update).toLocaleString("fr-FR")
    : "—";

  renderRecent(data.recent_positions);
  messageEl.textContent = data.db_available
    ? ""
    : "Base tablebase absente — initialisez-la puis lancez le worker Rust.";

  syncProcessFromStatus(data);
}

function syncProcessFromStatus(data) {
  const openingBook = isOpeningBookMode(data);
  const running = Boolean(data.solver_running);
  if (openingBook) {
    processBadgeEl.textContent = running ? "Livre d'ouverture actif" : "Build terminé";
    processBadgeEl.className = `status-badge ${running ? "status-running" : "status-done"}`;
    btnStartSolverEl.disabled = true;
    btnStopSolverEl.disabled = true;
    return;
  }
  processBadgeEl.textContent = running ? "Solveur actif" : "Solveur arrêté";
  processBadgeEl.className = `status-badge ${running ? "status-running" : "status-paused"}`;
  btnStartSolverEl.disabled = running;
  btnStopSolverEl.disabled = !running;
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
  if (isOpeningBookMode(data) || data.build_mode === "opening_book") {
    syncProcessFromStatus({ ...data, solver_running: data.running, build_mode: "opening_book" });
    return;
  }
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
  } catch {
    /* statut principal via /api/solver/status */
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
    for (let i = 0; i < 8; i++) {
      await new Promise((r) => setTimeout(r, 400));
      await pollProcessStatus();
      await poll();
    }
  }
}

btnStartSolverEl.addEventListener("click", () => {
  postLocalAction("/api/local/start-solver", "Solveur démarré.");
});

btnStopSolverEl.addEventListener("click", () => {
  postLocalAction("/api/local/stop-solver", "Solveur mis en pause.");
});

poll();
pollProcessStatus();
setInterval(poll, POLL_MS);
setInterval(pollProcessStatus, PROCESS_POLL_MS);
