import { Link } from "react-router-dom";
import Card from "../components/ui/Card";

const sections = [
  {
    to: "/play",
    title: "Jouer",
    desc: "Affrontez les bots, vos amis ou des joueurs en ligne.",
    emoji: "♟️",
  },
  {
    to: "/learn",
    title: "Apprendre",
    desc: "Ouvertures, puzzles tactiques, entraîneur et leçons.",
    emoji: "🎓",
  },
  {
    to: "/analyze",
    title: "Analyser",
    desc: "Revue de partie : précision, erreurs, meilleurs coups.",
    emoji: "🔎",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-10">
      <section className="text-center">
        <h1 className="text-4xl font-black tracking-tight text-accent drop-shadow-[0_0_12px_rgba(17,241,204,0.4)] sm:text-5xl">
          4mation
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-white/70">
          Alignez 4 pions adjacents sur un plateau 7×7. Jouez, progressez et analysez —
          propulsé par un solveur exact de 24 millions de positions.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link
            to="/play"
            className="rounded-lg bg-accent px-6 py-3 font-bold text-deep transition hover:bg-accent-hover hover:-translate-y-px"
          >
            Jouer maintenant
          </Link>
          <Link
            to="/learn"
            className="rounded-lg border border-accent px-6 py-3 font-bold text-accent transition hover:bg-accent/10"
          >
            Apprendre
          </Link>
        </div>
      </section>

      <section className="grid gap-5 sm:grid-cols-3">
        {sections.map((s) => (
          <Link key={s.to} to={s.to} className="group">
            <Card className="h-full transition group-hover:border-accent/50 group-hover:bg-white/[0.07]">
              <div className="text-3xl">{s.emoji}</div>
              <h2 className="mt-3 text-xl font-bold text-accent">{s.title}</h2>
              <p className="mt-1 text-sm text-white/70">{s.desc}</p>
            </Card>
          </Link>
        ))}
      </section>
    </div>
  );
}
