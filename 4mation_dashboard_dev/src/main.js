/**
 * Client jeu 4mation — Partie classique + mode Apprentissage (MCTS)
 */

import { setupLab211Auth } from "./lab211-auth-setup.js";

const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const SESSION_KEY = "4mation_session_id";
const MODE_KEY = "4mation_mode";
const MCTS_BUDGET_MS = 600;

/** @type {string | null} */
let sessionId = localStorage.getItem(SESSION_KEY);
/** @type {string} */
let selectedBotId = localStorage.getItem("4mation_bot_id") || "minimax_d4";
/** @type {"standard"|"learning"} */
let gameMode = localStorage.getItem(MODE_KEY) || "standard";
/** @type {boolean} */
let autoAiAfterHuman = true;
/** @type {boolean} */
let isBusy = false;
/** @type {Record<string, number> | null} */
let mctsRates = null;
/** @type {string} */
let analysisLabel = "Estimé (MCTS)";
/** @type {boolean} */
let analysisExact = false;
/** @type {{row:number,col:number}|null} */
let bestMove = null;
/** @type {any} */
let lastRenderedState = null;
/** @type {number} */
let analysisToken = 0;
/** Afficher la surbrillance du meilleur coup (étoile) sur le plateau. */
const showBestMove = true;

const boardEl = document.getElementById("board");
const messageEl = document.getElementById("message");
const gameInfoEl = document.getElementById("game-info");
const timelineEl = document.getElementById("timeline");
const botSelectEl = document.getElementById("bot-select");
const modeSelectEl = document.getElementById("mode-select");
const botFieldEl = document.getElementById("bot-field");
const btnNew = document.getElementById("btn-new");
const btnAi = document.getElementById("btn-ai");
const btnUndo = document.getElementById("btn-undo");
const btnVariant = document.getElementById("btn-variant");
const authSlotEl = document.getElementById("auth-slot");
const winbarEl = document.getElementById("winbar");
const winbarFillEl = document.getElementById("winbar-fill");
const winbarLabelEl = document.getElementById("winbar-label");
const winbarSourceEl = document.getElementById("winbar-source");
const winbarPctP1El = document.getElementById("winbar-pct-p1");
const winbarPctP2El = document.getElementById("winbar-pct-p2");

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function authHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (sessionId) {
    headers["X-Session-Id"] = sessionId;
  }
  return headers;
}

function setBusy(busy, label = "") {
  isBusy = busy;
  boardEl.classList.toggle("thinking", busy);
  document.body.classList.toggle("is-busy", busy);
  if (busy && label) {
    messageEl.textContent = label;
  }
  btnNew.disabled = busy;
  btnUndo.disabled = busy || btnUndo.disabled;
  btnVariant.disabled = busy || btnVariant.disabled;
}

async function apiFetch(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
    credentials: "include",
  });

  const headerSession = response.headers.get("X-Session-Id");
  if (headerSession) {
    sessionId = headerSession;
    localStorage.setItem(SESSION_KEY, sessionId);
  }

  const data = await response.json().catch(() => ({}));

  if (
    response.status === 404 &&
    data.error === "Session introuvable" &&
    !options._sessionRetry
  ) {
    sessionId = null;
    localStorage.removeItem(SESSION_KEY);
    await ensureSession();
    return apiFetch(path, { ...options, _sessionRetry: true });
  }

  if (!response.ok) {
    throw new Error(data.error || `Erreur HTTP ${response.status}`);
  }
  return data;
}

async function ensureSession() {
  if (sessionId) {
    return sessionId;
  }
  const data = await apiFetch("/api/session", {
    method: "POST",
    body: JSON.stringify({ mode: gameMode }),
  });
  sessionId = data.session_id;
  localStorage.setItem(SESSION_KEY, sessionId);
  return sessionId;
}

async function loadBots() {
  const data = await apiFetch("/api/bots");
  botSelectEl.innerHTML = "";
  for (const bot of data.bots) {
    const option = document.createElement("option");
    option.value = bot.id;
    option.textContent = bot.name;
    option.title = bot.description;
    if (bot.id === selectedBotId) {
      option.selected = true;
    }
    botSelectEl.appendChild(option);
  }
}

function cellKey(row, col) {
  return `${row},${col}`;
}

function renderTimeline(history) {
  timelineEl.innerHTML = "";
  if (!history?.length) {
    return;
  }
  for (const entry of history) {
    const li = document.createElement("li");
    const playerLabel = entry.player === 1 ? "Vous" : gameMode === "learning" ? "Coach" : "IA";
    li.textContent = `#${entry.index} — ${playerLabel} : (${entry.row + 1}, ${entry.col + 1})`;
    timelineEl.appendChild(li);
  }
}

function updateModeUI() {
  const isLearning = gameMode === "learning";
  botFieldEl.style.display = isLearning ? "none" : "";
  btnAi.style.display = isLearning ? "none" : "";
  modeSelectEl.value = gameMode;
}

function renderBoard(state) {
  if (!state?.board) {
    messageEl.textContent = "État de partie indisponible";
    return;
  }

  const { board, valid_actions: validActions, is_terminal: isTerminal, current_player: currentPlayer } = state;
  const lastMove = state.last_move;
  boardEl.innerHTML = "";

  for (let row = 0; row < board.length; row++) {
    for (let col = 0; col < board[row].length; col++) {
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "cell";
      cell.dataset.row = String(row);
      cell.dataset.col = String(col);
      cell.setAttribute("aria-label", `Case ${row + 1}, ${col + 1}`);

      const player = board[row][col];
      if (player === 1) cell.classList.add("player-1");
      if (player === 2) cell.classList.add("player-2");

      if (lastMove && lastMove.row === row && lastMove.col === col) {
        cell.classList.add("last-move");
      }

      if (showBestMove && bestMove && bestMove.row === row && bestMove.col === col && !isTerminal) {
        cell.classList.add("best-move");
      }

      const isValid = validActions?.some((a) => a.row === row && a.col === col);
      if (!isTerminal && currentPlayer === 1 && isValid && !isBusy) {
        cell.classList.add("playable");
        cell.addEventListener("click", () => playHumanMove(row, col));

        if (gameMode === "learning" && mctsRates) {
          const rate = mctsRates[cellKey(row, col)];
          if (rate !== undefined) {
            const pct = (rate * 100).toFixed(0);
            const suffix = analysisExact ? "exact" : "MCTS";
            cell.setAttribute("data-mcts", `${pct}%`);
            cell.title = `${pct}% victoire (${analysisLabel})`;
            cell.classList.toggle("exact-rate", analysisExact);
          }
        }
      }

      boardEl.appendChild(cell);
    }
  }

  const canUndo = (state.move_count ?? 0) > 0 && !isTerminal;
  btnUndo.disabled = isBusy || !canUndo;
  btnVariant.disabled = isBusy || !canUndo;

  renderTimeline(state.history);

  if (isBusy) {
    return;
  }

  if (isTerminal) {
    if (state.winner === 1) messageEl.textContent = "Vous avez gagné !";
    else if (state.winner === 2) messageEl.textContent = gameMode === "learning" ? "Le coach a gagné." : "L'IA a gagné.";
    else messageEl.textContent = "Match nul.";
    btnAi.disabled = true;
  } else if (currentPlayer === 1) {
    const count = validActions?.length ?? 0;
    if (gameMode === "learning") {
      messageEl.textContent =
        count === 49
          ? "Mode apprentissage — premier coup libre"
          : `À vous — % victoire (${analysisLabel}) sur les cases jouables`;
    } else {
      messageEl.textContent =
        count === 49
          ? "Premier coup — cliquez où vous voulez"
          : `À vous de jouer (${count} case${count > 1 ? "s" : ""} valide${count > 1 ? "s" : ""})`;
    }
    btnAi.disabled = true;
  } else {
    messageEl.textContent = gameMode === "learning" ? "Le coach réfléchit…" : "Tour de l'IA…";
    btnAi.disabled = false;
  }

  gameInfoEl.textContent = `Coup #${state.move_count} — Joueur actif : ${currentPlayer}`;
}

function updateWinBar(winRateP1, label, exact) {
  const p1 = Math.max(0, Math.min(1, Number.isFinite(winRateP1) ? winRateP1 : 0.5));
  const pct1 = Math.round(p1 * 100);
  winbarEl.hidden = false;
  winbarFillEl.style.width = `${pct1}%`;
  winbarPctP1El.textContent = `${pct1}%`;
  winbarPctP2El.textContent = `${100 - pct1}%`;
  winbarLabelEl.textContent = "Probabilité de victoire";
  winbarSourceEl.textContent = label || "";
  winbarEl.classList.toggle("is-exact", Boolean(exact));
}

/** Analyse non-bloquante : met à jour la barre W/L, le meilleur coup et (mode
 * apprentissage) les taux par case, puis redessine le plateau. */
async function runAnalysis() {
  const token = ++analysisToken;
  try {
    const data = await apiFetch("/api/analyze", {
      method: "POST",
      body: JSON.stringify({ time_budget_ms: MCTS_BUDGET_MS }),
    });
    if (token !== analysisToken) return; // résultat périmé (un coup plus récent a été joué)
    const analysis = data.analysis ?? {};
    analysisExact = Boolean(analysis.exact);
    analysisLabel = analysis.label || (analysisExact ? "Exact (tablebase)" : "Estimé (MCTS)");
    const rates = {};
    for (const m of analysis.moves ?? []) {
      rates[cellKey(m.row, m.col)] = m.win_rate;
    }
    mctsRates = gameMode === "learning" ? rates : null;
    bestMove = Array.isArray(analysis.best_move)
      ? { row: analysis.best_move[0], col: analysis.best_move[1] }
      : null;
    const wrP1 = typeof analysis.win_rate_p1 === "number" ? analysis.win_rate_p1 : 0.5;
    updateWinBar(wrP1, analysisLabel, analysisExact);
    if (lastRenderedState) renderBoard(lastRenderedState);
  } catch {
    if (token === analysisToken) {
      winbarSourceEl.textContent = "analyse indisponible";
    }
  }
}

/** Applique un nouvel état : rendu immédiat propre, puis analyse asynchrone. */
function applyState(state) {
  if (!state) return;
  lastRenderedState = state;
  bestMove = null;
  mctsRates = null;
  renderBoard(state);
  if (state.is_terminal) {
    const w = state.winner;
    updateWinBar(w === 1 ? 1 : w === 2 ? 0 : 0.5, "Partie terminée", true);
    return;
  }
  runAnalysis();
}

async function refreshState() {
  await ensureSession();
  const state = await apiFetch("/api/state");
  if (state.mode) {
    gameMode = state.mode;
    updateModeUI();
  }
  applyState(state);
  return state;
}

async function requestAiMove() {
  setBusy(true, "Réflexion de l'IA…");
  btnAi.disabled = true;
  try {
    return await apiFetch("/api/ai_move", {
      method: "POST",
      body: JSON.stringify({ bot_id: selectedBotId }),
    });
  } catch (error) {
    messageEl.textContent = `L'IA n'a pas pu jouer : ${error.message}`;
    await refreshState().catch(() => {});
    return null;
  } finally {
    setBusy(false);
  }
}

async function playHumanMove(row, col) {
  if (isBusy) return;
  let latestState = null;
  try {
    setBusy(true, "Coup en cours…");
    const data = await apiFetch("/api/move", {
      method: "POST",
      body: JSON.stringify({ action: { row, col } }),
    });
    latestState = data.state;

    if (autoAiAfterHuman && !data.terminal && data.next_player === 2) {
      setBusy(false);
      const aiData = await requestAiMove();
      if (aiData?.state) {
        latestState = aiData.state;
      }
      return;
    }
  } catch (error) {
    messageEl.textContent = `Erreur : ${error.message}`;
    await refreshState().catch(() => {});
    return;
  } finally {
    setBusy(false);
    if (latestState) {
      applyState(latestState);
    }
  }
}

async function playAiMove() {
  if (isBusy) return;
  const data = await requestAiMove();
  if (data?.state) {
    applyState(data.state);
  }
}

async function newGame() {
  if (isBusy) return;
  try {
    setBusy(true, "Nouvelle partie…");
    await ensureSession();
    const data = await apiFetch("/api/reset", {
      method: "POST",
      body: JSON.stringify({ mode: gameMode }),
    });
    applyState(data.state);
  } catch (error) {
    messageEl.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function undoMove() {
  if (isBusy) return;
  try {
    setBusy(true, "Annulation…");
    const data = await apiFetch("/api/undo", {
      method: "POST",
      body: JSON.stringify({ count: 1 }),
    });
    applyState(data.state);
  } catch (error) {
    messageEl.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function newVariant() {
  if (isBusy) return;
  try {
    setBusy(true, "Nouvelle variante…");
    const state = await apiFetch("/api/state");
    const count = Math.max(0, (state.move_count ?? 1) - 1);
    const data = await apiFetch("/api/undo_to", {
      method: "POST",
      body: JSON.stringify({ move_index: count }),
    });
    applyState(data.state);
    messageEl.textContent = "Nouvelle variante — rejouez à partir d'ici";
  } catch (error) {
    messageEl.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function switchMode() {
  gameMode = modeSelectEl.value;
  localStorage.setItem(MODE_KEY, gameMode);
  updateModeUI();
  sessionId = null;
  localStorage.removeItem(SESSION_KEY);
  mctsRates = null;
  await newGame();
}

botSelectEl.addEventListener("change", () => {
  selectedBotId = botSelectEl.value;
  localStorage.setItem("4mation_bot_id", selectedBotId);
});

modeSelectEl.addEventListener("change", switchMode);
btnNew.addEventListener("click", newGame);
btnAi.addEventListener("click", playAiMove);
btnUndo.addEventListener("click", undoMove);
btnVariant.addEventListener("click", newVariant);
async function init() {
  setupLab211Auth(authSlotEl);
  updateModeUI();
  try {
    await loadBots();
    await refreshState();
  } catch (error) {
    messageEl.textContent = `Impossible de joindre l'API : ${error.message}`;
  }
}

init();
