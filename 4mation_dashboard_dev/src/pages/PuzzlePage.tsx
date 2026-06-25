import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Board, { emptyBoard } from "../components/game/Board";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import {
  checkPuzzle,
  exploreOpening,
  fetchRandomPuzzle,
  type Puzzle,
} from "../lib/learnApi";

function boardFromHistory(history: { row: number; col: number; player: number }[]) {
  const board = emptyBoard();
  for (const h of history) {
    board[h.row][h.col] = h.player;
  }
  return board;
}

export default function PuzzlePage() {
  const [puzzle, setPuzzle] = useState<Puzzle | null>(null);
  const [playable, setPlayable] = useState<{ row: number; col: number }[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [solved, setSolved] = useState(false);
  const [solutionMove, setSolutionMove] = useState<{ row: number; col: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadPuzzle = useCallback(async () => {
    setBusy(true);
    setFeedback(null);
    setSolved(false);
    setSolutionMove(null);
    setError(null);
    try {
      const p = await fetchRandomPuzzle();
      setPuzzle(p);
      const moves = p.history.map((h) => ({ row: h.row, col: h.col }));
      const explore = await exploreOpening(moves);
      setPlayable(explore.continuations.map((c) => c.move));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de charger un puzzle");
      setPuzzle(null);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void loadPuzzle();
  }, [loadPuzzle]);

  const onCellClick = async (row: number, col: number) => {
    if (!puzzle || busy || solved) return;
    setBusy(true);
    setFeedback(null);
    try {
      const res = await checkPuzzle(puzzle, { row, col });
      if (res.correct) {
        setSolved(true);
        setSolutionMove({ row, col });
        setFeedback(
          res.note === "acceptable"
            ? "Correct (coup acceptable)."
            : `Excellent ! ${Math.round((res.win_rate ?? puzzle.win_rate) * 100)}% de victoire.`
        );
      } else {
        setSolutionMove(res.solution ?? puzzle.solution);
        setFeedback("Raté — voici le meilleur coup.");
      }
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(false);
    }
  };

  const board = puzzle ? boardFromHistory(puzzle.history) : emptyBoard();
  const lastMove =
    puzzle && puzzle.history.length
      ? {
          row: puzzle.history[puzzle.history.length - 1].row,
          col: puzzle.history[puzzle.history.length - 1].col,
        }
      : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div>
        <Board
          board={board}
          playable={solved ? [] : playable}
          lastMove={lastMove}
          bestMove={solved ? solutionMove : null}
          thinking={busy}
          onCellClick={({ row, col }) => void onCellClick(row, col)}
        />
        <p className="mt-4 text-center text-lg font-semibold text-accent">
          {puzzle
            ? solved
              ? feedback
              : `Joueur ${puzzle.player_to_move} — trouvez le meilleur coup`
            : "Chargement…"}
        </p>
        {error && <p className="mt-2 text-center text-sm text-p1">{error}</p>}
      </div>

      <aside className="space-y-4">
        <Link to="/learn" className="text-sm text-white/50 hover:text-accent">
          ← Apprendre
        </Link>
        <h1 className="text-2xl font-black text-accent">Puzzles</h1>

        <Card>
          <h2 className="mb-2 text-sm font-bold uppercase tracking-wide text-white/50">
            Indice
          </h2>
          {puzzle ? (
            <ul className="space-y-1 text-sm text-white/70">
              <li>Thème : {puzzle.theme}</li>
              <li>Écart tactique : {Math.round(puzzle.gap * 100)} pts</li>
              <li>
                Meilleur coup : ~{Math.round(puzzle.win_rate * 100)}% victoire
              </li>
              {puzzle.label && <li className="text-xs text-white/50">{puzzle.label}</li>}
            </ul>
          ) : (
            <p className="text-sm text-white/50">—</p>
          )}
        </Card>

        <Button onClick={() => void loadPuzzle()} disabled={busy}>
          Nouveau puzzle
        </Button>
      </aside>
    </div>
  );
}
