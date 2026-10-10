import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Card from "../components/ui/Card";
import RuleDiagram, { type CellValue } from "../components/learn/RuleDiagram";
import { fetchLessons, type Lesson, type LessonDiagram } from "../lib/learnApi";

/**
 * Premier schéma d'une leçon, s'il existe.
 *
 * Le catalogue ne duplique pas les positions : il affiche le schéma réel de la leçon,
 * celui qu'on retrouvera dans le corps du texte. Ajouter un schéma à une leçon suffit
 * donc à enrichir sa vignette.
 */
function firstDiagram(lesson: Lesson): LessonDiagram | null {
  for (const section of lesson.sections) {
    if (section.diagram) return section.diagram;
  }
  return null;
}

export default function LessonsPage() {
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchLessons()
      .then(setLessons)
      .catch((err) => setError(err instanceof Error ? err.message : "Erreur"));
  }, []);

  return (
    <div className="space-y-6">
      <Link to="/learn" className="inline-block py-2 text-sm text-white/60 hover:text-accent">
        ← Apprendre
      </Link>
      <header>
        <h1 className="text-2xl font-black text-accent">Leçons</h1>
        <p className="mt-1 text-sm text-white/60">
          Principes fondamentaux du 4mation, du débutant à l'expert.
        </p>
      </header>

      {error && <p className="text-sm text-p1">{error}</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        {lessons.map((l) => {
          const diagram = firstDiagram(l);
          return (
            <Link key={l.id} to={`/learn/lessons/${l.id}`} className="group">
              <Card className="flex h-full flex-col transition group-hover:border-accent/50">
                <span className="text-xs font-bold uppercase text-white/60">{l.level}</span>
                <h2 className="mt-1 text-lg font-bold text-accent">{l.title}</h2>
                <p className="mt-2 text-sm text-white/60">~{l.duration_min} min</p>
                {/* Vignette masquée sur téléphone : la liste restait trop longue à parcourir */}
                {diagram && (
                  <div className="mt-auto hidden justify-center pt-4 sm:flex">
                    <RuleDiagram
                      compact
                      board={diagram.board as CellValue[][]}
                      highlights={diagram.highlights}
                      labels={diagram.labels}
                      winLine={diagram.win_line}
                    />
                  </div>
                )}
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
