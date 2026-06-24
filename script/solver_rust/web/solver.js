/**
 * Dashboard solveur local — même API que la prod (/api/solver/status, /api/solver/work/stats).
 */

const POLL_MS = 2500;

const progressBarEl = document.getElementById("progress-bar");
const progressPctEl = document.getElementById("progress-pct");
const statusBadgeEl = document.getElementById("status-badge");
const statSolvedEl = document.getElementById("stat-solved");
const statTargetEl = document.getElementById("stat-target");
const statRateEl = document.getElementById("stat-rate");
const statEtaEl = document.getElementById("stat-eta");
const statDurationEl = document.getElementById("stat-duration");
const statPhaseEl = document.getElementById("stat-phase");
const statUpdatedEl = document.getElementById("stat-updated");
const recentGridEl = document.getElementById("recent-grid");
const messageEl = document.getElementById("message");
const statQueuePendingEl = document.getElementById("stat-queue-pending");
const statQueueProgressEl = document.getElementById("stat-queue-progress");
const statWorkerCountEl = document.getElementById("stat-worker-count");
const workersListEl = document.getElementById("workers-list");
const processBadgeEl = document.getElementById("process-badge");
const btnStartSolverEl = document.getElementById("btn-start-solver");
const btnStopSolverEl = document.getElementById("btn-stop-solver");
const controlsMessageEl = document.getElementById("controls-message");

const PROCESS_POLL_MS = 3000;

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const hint = response.status === 404
      ? " — route absente (relancez scripts\\run_local_solver_stack.bat ou run_local_dashboard.bat)"
      : "";
    throw new Error(`Réponse non-JSON (HTTP ${response.status})${hint}`);
  }
  const data = await response.json();
  return { response, data };
}

function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h} h ${m} min`;
  if (m > 0) return `${m} min ${sec} s`;
  return `${sec} s`;
}

function formatEta(seconds) {
  if (seconds == null) return "—";
  return `~${formatDuration(seconds)}`;
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
      if (best && best.row === row && best.col === col) {
        cell.classList.add("best-move");
      }
      if (last && last.row === row && last.col === col) {
        cell.classList.add("last-move");
      }
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

function formatProgressPercent(pct, solved, unknown) {
  const solvedCount = solved ?? 0;
  if (unknown || pct == null) {
    if (solvedCount > 0) {
      return `${solvedCount.toLocaleString("fr-FR")} résolues (exploration en cours)`;
    }
    return "—";
  }
  const value = Math.min(100, Math.max(0, pct));
  if (value > 0 && value < 0.1) {
    return value < 0.01 ? "< 0,01 %" : `${value.toFixed(2).replace(".", ",")} %`;
  }
  if (value === 0 && solvedCount > 0) {
    return `${solvedCount.toLocaleString("fr-FR")} résolues`;
  }
  return `${value.toFixed(1).replace(".", ",")} %`;
}

function renderWorkers(stats) {
  if (!stats) {
    statQueuePendingEl.textContent = "—";
    statQueueProgressEl.textContent = "—";
    statWorkerCountEl.textContent = "—";
    workersListEl.innerHTML = '<li class="muted">Stats file indisponibles</li>';
    return;
  }

  statQueuePendingEl.textContent = (stats.pending ?? 0).toLocaleString("fr-FR");
  statQueueProgressEl.textContent = (stats.in_progress ?? 0).toLocaleString("fr-FR");
  statWorkerCountEl.textContent = String(stats.active_worker_count ?? 0);

  const workers = stats.active_workers || [];
  if (!workers.length) {
    workersListEl.innerHTML =
      '<li class="muted">Aucun worker actif — lancez <code>4mation-worker --local-db</code>.</li>';
    return;
  }

  workersListEl.innerHTML = "";
  for (const w of workers) {
    const li = document.createElement("li");
    const last = w.last_claim
      ? new Date(w.last_claim.replace(" ", "T") + "Z").toLocaleString("fr-FR")
      : "—";
    li.textContent = `${w.worker_id} — ${w.positions_in_progress} pos. (dernier claim : ${last})`;
    workersListEl.appendChild(li);
  }
}

function updateUI(data) {
  const solved = data.total_positions_solved ?? 0;
  const pct = data.progress_unknown ? null : (data.progress_percent ?? 0);
  const barPct = pct == null ? 0 : Math.min(100, Math.max(0, pct));
  const displayPct = formatProgressPercent(pct, solved, data.progress_unknown);

  progressBarEl.style.width = `${barPct}%`;
  progressBarEl.setAttribute("aria-valuenow", String(barPct));
  progressPctEl.textContent = displayPct;
  progressPctEl.title =
    solved > 0
      ? `${solved.toLocaleString("fr-FR")} position${solved > 1 ? "s" : ""} résolue${solved > 1 ? "s" : ""}`
      : "";

  const badge = statusLabel(data.status);
  statusBadgeEl.textContent = badge.text;
  statusBadgeEl.className = `status-badge ${badge.cls}`;

  statSolvedEl.textContent = (data.total_positions_solved ?? 0).toLocaleString("fr-FR");
  const targetLabel =
    data.progress_unknown || data.total_positions_target == null
      ? "estimation en cours"
      : `~${data.total_positions_target.toLocaleString("fr-FR")}`;
  statTargetEl.textContent = targetLabel;
  statRateEl.textContent =
    data.positions_per_second > 0
      ? `${data.positions_per_second.toLocaleString("fr-FR")} /s`
      : "—";
  statEtaEl.textContent = formatEta(data.eta_seconds);
  statDurationEl.textContent = formatDuration(elapsedSince(data.started_at));
  statPhaseEl.textContent = phaseLabel(data.current_phase, data.phase_label);
  statUpdatedEl.textContent = data.last_update
    ? new Date(data.last_update).toLocaleString("fr-FR")
    : "—";

  renderRecent(data.recent_positions);
  if (!data.db_available) {
    messageEl.textContent =
      "Base tablebase absente — initialisez-la (seed) puis lancez le worker Rust.";
  } else {
    messageEl.textContent = "";
  }
}

async function pollWorkers() {
  try {
    const { response, data } = await fetchJson("/api/solver/work/stats");
    if (response.ok && data.success) {
      renderWorkers(data);
    }
  } catch {
    renderWorkers(null);
  }
}

async function poll() {
  try {
    const { response, data } = await fetchJson("/api/solver/status");
    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
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

async function pollProcessStatus() {
  try {
    const { response, data } = await fetchJson("/api/local/process-status");
    if (response.ok && data.success) {
      renderProcessStatus(data);
      setControlsMessage("");
      return;
    }
    throw new Error(data.error || `HTTP ${response.status}`);
  } catch (error) {
    processBadgeEl.textContent = "État indisponible";
    processBadgeEl.className = "status-badge status-paused";
    btnStartSolverEl.disabled = false;
    btnStopSolverEl.disabled = true;
    setControlsMessage(error.message, true);
  }
}

function setControlsMessage(text, isError = false) {
  controlsMessageEl.textContent = text || "";
  controlsMessageEl.classList.toggle("message", Boolean(isError));
  controlsMessageEl.classList.toggle("muted", !isError);
}

async function postLocalAction(url, successFallback) {
  setControlsMessage("");
  btnStartSolverEl.disabled = true;
  btnStopSolverEl.disabled = true;
  try {
    const { response, data } = await fetchJson(url, { method: "POST" });
    if (!response.ok || !data.success) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    setControlsMessage(data.message || successFallback);
    await pollProcessStatus();
  } catch (error) {
    setControlsMessage(error.message, true);
    await pollProcessStatus();
  }
}

btnStartSolverEl.addEventListener("click", () => {
  postLocalAction("/api/local/start-solver", "Solveur lancé.");
});

btnStopSolverEl.addEventListener("click", () => {
  if (!window.confirm("Arrêter le processus 4mation-local.exe ?")) {
    return;
  }
  postLocalAction("/api/local/stop-solver", "Arrêt demandé.");
});

pollProcessStatus();
setInterval(pollProcessStatus, PROCESS_POLL_MS);

poll();
pollWorkers();
setInterval(poll, POLL_MS);
setInterval(pollWorkers, POLL_MS);
