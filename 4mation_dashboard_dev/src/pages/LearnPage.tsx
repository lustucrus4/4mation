import { Link } from "react-router-dom";
import Card from "../components/ui/Card";

const bricks = [
  {
    to: "/learn/rules",
    title: "Règles",
    desc: "Les règles expliquées pas à pas avec des schémas visuels.",
    emoji: "📋",
  },
  {
    to: "/learn/openings",
    title: "Ouvertures",
    desc: "Explorez l'arbre des ouvertures et leurs taux de victoire.",
    emoji: "📖",
  },
  {
    to: "/learn/puzzles",
    title: "Puzzles",
    desc: "Tactiques auto-générées depuis la tablebase.",
    emoji: "🧩",
  },
  {
    to: "/learn/trainer",
    title: "Entraîneur",
    desc: "Jouez avec indices et % de victoire sur chaque case.",
    emoji: "🧠",
  },
  {
    to: "/learn/lessons",
    title: "Leçons",
    desc: "Principes du jeu pas à pas.",
    emoji: "🎓",
  },
];

export default function LearnPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-black text-accent">Apprendre</h1>
        <p className="mt-1 text-sm text-white/60">
          Règles illustrées, ouvertures, puzzles, entraînement guidé et leçons.
        </p>
      </header>
      <div className="grid gap-5 sm:grid-cols-2">
        {bricks.map((b) => (
          <Link key={b.to} to={b.to} className="group">
            <Card className="h-full transition group-hover:border-accent/50 group-hover:bg-white/[0.07]">
              <div className="text-3xl">{b.emoji}</div>
              <h2 className="mt-3 text-xl font-bold text-accent">{b.title}</h2>
              <p className="mt-1 text-sm text-white/70">{b.desc}</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
