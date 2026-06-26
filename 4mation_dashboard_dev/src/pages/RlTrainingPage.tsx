import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRlMetrics, fetchRlStatus } from "../lib/rlApi";

function pct(v: number | undefined | null): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(1)} %`;
}

function fmtEta(sec: number | undefined | null): string {
  if (sec == null || sec <= 0) return "—";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h} h ${m} min`;
  return `${m} min`;
}

function MiniBar({ value, max, color }: { value: number; max: number; color: string }) {
  const w = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-2 w-full rounded-full bg-white/10">
      <div className="h-2 rounded-full transition-all" style={{ width: `${w}%`, background: color }} />
    </div>
  );
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (values.length < 2) {
    return <p className="text-sm text-white/40">Pas assez de données</p>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const w = 320;
  const h = 64;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full max-w-md text-accent">
      <polyline fill="none" stroke={color} strokeWidth="2" points={pts} />
    </svg>
  );
}

export default function RlTrainingPage() {
  const statusQ = useQuery({
    queryKey: ["rl-status"],
    queryFn: fetchRlStatus,
    refetchInterval: 5000,
  });
  const metricsQ = useQuery({
    queryKey: ["rl-metrics"],
    queryFn: () => fetchRlMetrics(400),
    refetchInterval: 10000,
  });

  const status = statusQ.data;
  const metrics = metricsQ.data ?? [];

  const selfPlay = metrics.filter((m) => m.event === "self_play");
  const evals = metrics.filter((m) => m.event === "eval_level5" && m.eval_vs_level5 != null);

  const winRates = selfPlay.map((m) => m.self_play_win_rate_p1 ?? 0);
  const evalRates = evals.map((m) => m.eval_vs_level5 ?? 0);
  const steps = selfPlay.map((m) => m.step);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-black text-accent">Entraînement RL (Rust)</h1>
        <p className="mt-2 max-w-2xl text-white/60">
          Self-play parallèle · policy linéaire + MCTS-lite · évaluation périodique vs Minimax
          level_5 (tablebase).
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Statut" value={status?.running ? "Actif" : "Arrêté"} accent={status?.running} />
        <StatCard label="Step" value={String(status?.step ?? 0)} />
        <StatCard label="Parties jouées" value={String(status?.total_games ?? 0)} />
        <StatCard label="Débit" value={status?.games_per_sec ? `${status.games_per_sec.toFixed(0)} part./s` : "—"} />
        <StatCard label="Win rate self-play (J1)" value={pct(status?.last_self_play_win_rate)} />
        <StatCard label="Win rate vs level_5" value={pct(status?.last_eval_vs_level5)} />
        <StatCard label="Cœurs rayon" value={String(status?.cores ?? "—")} />
        <StatCard label="ETA" value={fmtEta(status?.eta_seconds)} />
      </section>

      {status?.message && (
        <p className="rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/70">
          {status.message}
          {status.checkpoint && (
            <span className="mt-1 block text-xs text-white/40">Checkpoint : {status.checkpoint}</span>
          )}
        </p>
      )}

      <div className="grid gap-8 lg:grid-cols-2">
        <ChartBlock title="Win rate self-play (J1)" subtitle={`${winRates.length} points`}>
          <Sparkline values={winRates} color="#11f1cc" />
          {winRates.length > 0 && (
            <MiniBar value={winRates[winRates.length - 1] ?? 0} max={1} color="#11f1cc" />
          )}
        </ChartBlock>
        <ChartBlock title="Win rate vs Minimax level_5" subtitle={`${evalRates.length} évaluations`}>
          <Sparkline values={evalRates} color="#f97316" />
          {evalRates.length > 0 && (
            <MiniBar value={evalRates[evalRates.length - 1] ?? 0} max={1} color="#f97316" />
          )}
        </ChartBlock>
      </div>

      <section>
        <h2 className="mb-3 text-lg font-bold text-white/90">Dernières métriques</h2>
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-white/5 text-white/50">
              <tr>
                <th className="px-3 py-2">Step</th>
                <th className="px-3 py-2">Événement</th>
                <th className="px-3 py-2">Self-play WR</th>
                <th className="px-3 py-2">vs level_5</th>
                <th className="px-3 py-2">part./s</th>
              </tr>
            </thead>
            <tbody>
              {[...metrics].reverse().slice(0, 20).map((m, i) => (
                <tr key={`${m.step}-${m.event}-${i}`} className="border-t border-white/5">
                  <td className="px-3 py-2 font-mono">{m.step}</td>
                  <td className="px-3 py-2">{m.event}</td>
                  <td className="px-3 py-2">{pct(m.self_play_win_rate_p1)}</td>
                  <td className="px-3 py-2">{pct(m.eval_vs_level5)}</td>
                  <td className="px-3 py-2">{m.games_per_sec?.toFixed(1) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-xl border border-accent/20 bg-accent/5 p-4 text-sm text-white/70">
        <h3 className="font-bold text-accent">Lancer l&apos;entraînement</h3>
        <pre className="mt-2 overflow-x-auto rounded bg-black/40 p-3 text-xs text-white/80">
{`cd 4mation/script/rl_rust
cargo run --release --bin train -- --cores 16 --self-play-games 1000 --eval-every 5000
# ou en arrière-plan Windows :
..\\scripts\\run_rl_train.ps1`}
        </pre>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-white/45">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${accent ? "text-accent" : "text-white"}`}>{value}</p>
    </div>
  );
}

function ChartBlock({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h3 className="font-bold text-white/90">{title}</h3>
      <p className="text-xs text-white/40">{subtitle}</p>
      <div className="mt-4">{children}</div>
    </div>
  );
}
