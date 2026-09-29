import { Link } from "react-router-dom";
import Card from "../components/ui/Card";
import RuleDiagram from "../components/learn/RuleDiagram";
import {
  centerHeatmapDiagram,
  frontierDiagram,
  threatOnFrontierDiagram,
  turnOrderDiagram,
  winLastMoveDiagram,
} from "../components/learn/diagrams";
import type { LearnDiagram } from "../components/learn/diagrams";

/**
 * Chaque carte montre un aperçu du plateau qu'on y manipule : on sait ce qu'on va
 * apprendre avant de cliquer, et la page n'est plus une simple liste de titres.
 */
const bricks: {
  to: string;
  title: string;
  desc: string;
  emoji: string;
  diagram: LearnDiagram;
}[] = [
  {
    to: "/learn/rules",
    title: "Règles",
    desc: "Les règles expliquées pas à pas, avec des schémas visuels.",
    emoji: "📋",
    diagram: winLastMoveDiagram,
  },
  {
    to: "/learn/openings",
    title: "Ouvertures",
    desc: "Explorez l'arbre des ouvertures et leurs taux de victoire.",
    emoji: "📖",
    diagram: centerHeatmapDiagram,
  },
  {
    to: "/learn/puzzles",
    title: "Puzzles",
    desc: "Tactiques auto-générées depuis la tablebase.",
    emoji: "🧩",
    diagram: threatOnFrontierDiagram,
  },
  {
    to: "/learn/trainer",
    title: "Entraîneur",
    desc: "Jouez avec indices et % de victoire sur chaque case.",
    emoji: "🧠",
    diagram: frontierDiagram,
  },
  {
    to: "/learn/lessons",
    title: "Leçons",
    desc: "Principes du jeu pas à pas.",
    emoji: "🎓",
    diagram: turnOrderDiagram,
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
            <Card className="flex h-full flex-col transition group-hover:border-accent/50 group-hover:bg-white/[0.07]">
              <div className="flex items-start gap-3">
                <div className="text-3xl">{b.emoji}</div>
                <div>
                  <h2 className="text-xl font-bold text-accent">{b.title}</h2>
                  <p className="mt-1 text-sm text-white/70">{b.desc}</p>
                </div>
              </div>
              <div className="mt-auto flex justify-center pt-4">
                <RuleDiagram {...b.diagram} compact />
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
