import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Board, { emptyBoard } from "../components/game/Board";
import WinBar from "../components/game/WinBar";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import { exploreOpening, type OpeningExplore } from "../lib/learnApi";

export default function OpeningExplorerPage() {
  const [moves, setMoves] = useState<{ row: number; col: number }[]>([]);
  const [data, setData] = useState<OpeningExplore | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (nextMoves: { row: number; col: number }[]) => {
    setBusy(true);
    setError(null);
    try {
      const res = await exploreOpening(nextMoves);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh([]);
  }, [refresh]);

  const playMove = (row: number, col: number) => {
    if (busy || data?.is_terminal) return;
    const next = [...moves, { row, col }];
    setMoves(next);
    void refresh(next);
  };

  const undo = () => {
    if (busy || moves.length === 0) return;
    const next = moves.slice(0, -1);
    setMoves(next);
    void refresh(next);
  };

  const reset = () => {
    setMoves([]);
    void refresh([]);
  };

  const board = data?.board ?? emptyBoard();
  const playable = data?.is_terminal
    ? []
    : (data?.continuations ?? []).map((c) => c.move);
  const dimInvalid = !busy && !data?.is_terminal && (data?.move_count ?? 0) > 0;
  const muteEmpty = busy || !!data?.is_terminal;
  const rates: Record<string, number> = {};
  for (const c of data?.continuations ?? []) {
    if (typeof c.win_rate === "number") {
      rates[`${c.move.row},${c.move.col}`] = c.win_rate;
    }
  }
  const bestMove =
    data?.best_move && Array.isArray(data.best_move)
      ? { row: data.best_move[0], col: data.best_move[1] }
      : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_340px]">
      <div>
        <Board
          board={board}
          playable={playable}
          dimInvalid={dimInvalid}
          muteEmpty={muteEmpty}
          lastMove={data?.last_move ?? null}
          bestMove={bestMove}
          rates={Object.keys(rates).length ? rates : undefined}
          ratesExact={data?.book?.exact}
          thinking={busy}
          onCellClick={({ row, col }) => playMove(row, col)}
        />

        {data?.book && (
          <WinBar
            winRateP1={data.book.win_rate}
            label="Position dans le livre"
            source={data.book.source}
            exact={data.book.exact}
          />
        )}

        <p className="mt-4 text-center text-sm text-white/60">
          Coup #{data?.move_count ?? 0}
          {data?.is_terminal && " — Partie terminée"}
        </p>
        {error && <p className="mt-2 text-center text-sm text-p1">{error}</p>}
      </div>

      <aside className="space-y-4">
        <div className="flex items-center gap-3">
          <Link to="/learn" className="text-sm text-white/50 hover:text-accent">
            ← Apprendre
          </Link>
        </div>
        <h1 className="text-2xl font-black text-accent">Ouvertures</h1>

        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={undo} disabled={busy || moves.length === 0}>
            Retour
          </Button>
          <Button variant="ghost" onClick={reset} disabled={busy || moves.length === 0}>
            Réinitialiser
          </Button>
        </div>

        <Card>
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-white/50">
            Continuations
          </h2>
          {(data?.continuations ?? []).length === 0 ? (
            <p className="text-sm text-white/50">Aucune continuation.</p>
          ) : (
            <ul className="max-h-72 space-y-1.5 overflow-y-auto text-sm">
              {(data?.continuations ?? []).map((c) => {
                const wr =
                  typeof c.win_rate === "number" ? Math.round(c.win_rate * 100) : null;
                return (
                  <li
                    key={`${c.move.row},${c.move.col}`}
                    className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2"
                  >
                    <button
                      type="button"
                      disabled={busy || !!data?.is_terminal}
                      onClick={() => playMove(c.move.row, c.move.col)}
                      className="font-mono text-accent hover:underline disabled:opacity-50"
                    >
                      ({c.move.row + 1},{c.move.col + 1})
                    </button>
                    <span className="text-xs text-white/60">
                      {wr !== null ? `${wr}%` : "—"}
                      {c.in_book ? " · livre" : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        {data?.analysis_label && (
          <p className="text-xs text-white/50">{data.analysis_label}</p>
        )}
      </aside>
    </div>
  );
}
