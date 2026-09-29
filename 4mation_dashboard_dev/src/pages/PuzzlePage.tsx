import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Board, { emptyBoard } from "../components/game/Board";
import GameOverOverlay from "../components/game/GameOverOverlay";
import RuleDiagram from "../components/learn/RuleDiagram";
import { puzzleUniqueWinDiagram } from "../components/learn/diagrams";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { useGameOverOverlay } from "../hooks/useGameOverOverlay";
import {
  checkPackPuzzle,
  DIFFICULTY_LABELS,
  fetchPackPuzzle,
  fetchPackPuzzles,
  type PackPuzzle,
  type PackPuzzleSummary,
  type PuzzleMove,
} from "../lib/learnApi";
import { computeValidActions } from "../lib/validActions";

function boardFromHistory(history: PuzzleMove[]) {
  const board = emptyBoard();
  for (const h of history) {
    board[h.row][h.col] = h.player;
  }
  return board;
}

function humanStepCount(history: PuzzleMove[], setupLen: number) {
  return history.slice(setupLen).filter((m) => m.player === 1).length;
}

export default function PuzzlePage() {
  const [catalog, setCatalog] = useState<PackPuzzleSummary[]>([]);
  const [difficulty, setDifficulty] = useState<PackPuzzleSummary["difficulty"]>("easy");
  const [puzzle, setPuzzle] = useState<PackPuzzle | null>(null);
  const [sessionHistory, setSessionHistory] = useState<PuzzleMove[]>([]);
  const [playable, setPlayable] = useState<{ row: number; col: number }[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [solved, setSolved] = useState(false);
  const [mistakes, setMistakes] = useState(0);
  const [wrongMove, setWrongMove] = useState<{ row: number; col: number; message: string } | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);
  const {
    intro: gameOverOverlay,
    show: showGameOverOverlay,
    dismiss: dismissGameOverOverlay,
  } = useGameOverOverlay();
  const wasOutcomeRef = useRef<"idle" | "solved">("idle");

  const filtered = useMemo(
    () => catalog.filter((p) => p.difficulty === difficulty),
    [catalog, difficulty]
  );

  const setupLen = puzzle?.history.length ?? 0;
  const currentStep = puzzle ? humanStepCount(sessionHistory, setupLen) : 0;
  const totalSteps = puzzle?.min_moves ?? puzzle?.human_moves ?? 0;

  // Le plateau doit laisser jouer *tous* les coups légaux : s'appuyer sur le livre
  // d'ouvertures masquait des positions absentes et pouvait désactiver le coup gagnant.
  const refreshPlayable = useCallback((history: PuzzleMove[]) => {
    const board = boardFromHistory(history);
    const last = history.length ? history[history.length - 1] : null;
    setPlayable(
      computeValidActions(board, 1, last ? { row: last.row, col: last.col } : null)
    );
  }, []);

  const loadCatalog = useCallback(async () => {
    setError(null);
    try {
      const list = await fetchPackPuzzles();
      setCatalog(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de charger les puzzles");
      setCatalog([]);
    }
  }, []);

  const loadPuzzle = useCallback(
    async (id: string) => {
      dismissGameOverOverlay();
      wasOutcomeRef.current = "idle";
      setBusy(true);
      setFeedback(null);
      setSolved(false);
      setMistakes(0);
      setWrongMove(null);
      setError(null);
      try {
        const p = await fetchPackPuzzle(id);
        setPuzzle(p);
        setSessionHistory(p.history);
        await refreshPlayable(p.history);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Impossible de charger le puzzle");
        setPuzzle(null);
        setSessionHistory([]);
      } finally {
        setBusy(false);
      }
    },
    [refreshPlayable, dismissGameOverOverlay]
  );

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  useEffect(() => {
    if (!filtered.length) return;
    const currentInList = puzzle && filtered.some((p) => p.id === puzzle.id);
    if (!currentInList) {
      void loadPuzzle(filtered[0].id);
    }
  }, [filtered, puzzle, loadPuzzle]);

  const resetPuzzle = () => {
    if (!puzzle) return;
    dismissGameOverOverlay();
    wasOutcomeRef.current = "idle";
    setSessionHistory(puzzle.history);
    setSolved(false);
    setMistakes(0);
    setWrongMove(null);
    setFeedback(null);
    void refreshPlayable(puzzle.history);
  };

  const onCellClick = async (row: number, col: number) => {
    if (!puzzle || busy || solved) return;
    setBusy(true);
    setFeedback(null);
    setWrongMove(null);
    try {
      const res = await checkPackPuzzle(puzzle.id, sessionHistory, { row, col });
      if (!res.correct) {
        if (res.expected_step != null) {
          setMistakes((n) => n + 1);
          setWrongMove({ row, col, message: "Ce n'est pas le coup gagnant." });
        } else {
          setWrongMove({ row, col, message: res.reason ?? "Coup refusé." });
        }
        return;
      }

      const nextHistory = res.history ?? sessionHistory;
      setSessionHistory(nextHistory);
      await refreshPlayable(nextHistory);

      if (res.solved) {
        setSolved(true);
        setFeedback("Bravo ! Victoire forcée en jouant tous vos coups parfaitement.");
        return;
      }

      const step = res.step ?? currentStep + 1;
      if (res.opponent_move) {
        setFeedback(`Coup ${step}/${totalSteps} — l'adversaire a répondu. À vous.`);
      } else {
        setFeedback(`Coup ${step}/${totalSteps} — continuez.`);
      }
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(false);
    }
  };

  const goToNextPuzzle = useCallback(() => {
    if (!puzzle || filtered.length <= 1) return;
    const idx = filtered.findIndex((p) => p.id === puzzle.id);
    const next = filtered[(idx + 1) % filtered.length];
    void loadPuzzle(next.id);
  }, [filtered, loadPuzzle, puzzle]);

  useEffect(() => {
    if (solved && wasOutcomeRef.current !== "solved") {
      wasOutcomeRef.current = "solved";
      showGameOverOverlay({
        result: "win",
        subtitle: feedback ?? "Bravo ! Séquence parfaite.",
        opponentName: puzzle?.title ?? "Puzzle",
      });
      return;
    }
    if (!solved && wasOutcomeRef.current === "solved") {
      wasOutcomeRef.current = "idle";
      dismissGameOverOverlay();
    }
  }, [dismissGameOverOverlay, feedback, puzzle?.title, showGameOverOverlay, solved]);

  const board = boardFromHistory(sessionHistory);
  const lastMove =
    sessionHistory.length > 0
      ? {
          row: sessionHistory[sessionHistory.length - 1].row,
          col: sessionHistory[sessionHistory.length - 1].col,
        }
      : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div className="relative">
        <Board
          board={board}
          playable={solved || busy ? [] : playable}
          dimInvalid={!busy && !solved && sessionHistory.length > 0}
          muteEmpty={busy || solved}
          lastMove={lastMove}
          invalidMove={wrongMove ? { row: wrongMove.row, col: wrongMove.col } : null}
          thinking={busy}
          onCellClick={({ row, col }) => void onCellClick(row, col)}
        />

        {gameOverOverlay ? (
          <GameOverOverlay
            intro={gameOverOverlay}
            onDismiss={dismissGameOverOverlay}
            primaryAction={{
              label:
                solved && filtered.length > 1 ? "Puzzle suivant" : "Recommencer",
              onClick: () => {
                dismissGameOverOverlay();
                if (solved && filtered.length > 1) goToNextPuzzle();
                else resetPuzzle();
              },
            }}
          />
        ) : null}

        <p className="mt-4 text-center text-lg font-semibold text-accent">
          {gameOverOverlay
            ? null
            : puzzle
              ? solved
                ? feedback
                : `Joueur 1 — trouvez la séquence gagnante (${currentStep + 1}/${totalSteps})`
              : "Chargement…"}
        </p>
        {wrongMove && !solved && (
          <p className="mt-2 text-center text-sm font-semibold text-p1">
            {wrongMove.message} Rien n&apos;a été joué
            {mistakes > 1
              ? ` — ${mistakes} essais manqués, cherchez un autre coup.`
              : " — cherchez un autre coup."}
          </p>
        )}
        {error && <p className="mt-2 text-center text-sm text-p1">{error}</p>}
      </div>

      <aside className="space-y-4">
        <Link to="/learn" className="text-sm text-white/50 hover:text-accent">
          ← Apprendre
        </Link>
        <h1 className="text-2xl font-black text-accent">Puzzles</h1>
        <p className="text-sm text-white/60">
          Trouvez la suite de coups qui force la victoire. L&apos;adversaire répond automatiquement
          entre chaque coup.
        </p>

        <Card>
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-white/50">
            Le but
          </h2>
          <div className="flex justify-center">
            <RuleDiagram {...puzzleUniqueWinDiagram} compact />
          </div>
        </Card>

        <Card>
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-white/50">
            Difficulté
          </h2>
          <div className="flex flex-wrap gap-2">
            {(["easy", "medium", "hard"] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDifficulty(d)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  difficulty === d
                    ? "bg-accent text-black"
                    : "bg-white/10 text-white/70 hover:bg-white/20"
                }`}
              >
                {DIFFICULTY_LABELS[d]}
              </button>
            ))}
          </div>
        </Card>

        <Card>
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-white/50">
            Sélection
          </h2>
          {filtered.length ? (
            <ul className="max-h-48 space-y-1 overflow-y-auto text-sm">
              {filtered.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void loadPuzzle(p.id)}
                    className={`w-full rounded px-2 py-1 text-left transition ${
                      puzzle?.id === p.id
                        ? "bg-accent/20 text-accent"
                        : "text-white/70 hover:bg-white/10"
                    }`}
                  >
                    {p.title}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-white/50">Aucun puzzle disponible.</p>
          )}
        </Card>

        {puzzle && (
          <Card>
            <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-white/50">
              Indice
            </h2>
            <ul className="space-y-1 text-sm text-white/70">
              <li>Thème : {puzzle.theme}</li>
              <li>Coups à trouver : {puzzle.min_moves ?? puzzle.human_moves}</li>
              <li>Progression : {Math.min(currentStep, totalSteps)}/{totalSteps}</li>
              <li>Essais manqués : {mistakes}</li>
            </ul>
          </Card>
        )}

        <div className="flex flex-wrap gap-2">
          <Button onClick={resetPuzzle} disabled={busy || !puzzle}>
            Recommencer
          </Button>
          {filtered.length > 1 && puzzle && (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={goToNextPuzzle}
            >
              Puzzle suivant
            </Button>
          )}
        </div>
      </aside>
    </div>
  );
}
