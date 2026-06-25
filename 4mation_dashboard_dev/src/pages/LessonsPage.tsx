import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Card from "../components/ui/Card";
import { fetchLessons, type Lesson } from "../lib/learnApi";

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
      <Link to="/learn" className="text-sm text-white/50 hover:text-accent">
        ← Apprendre
      </Link>
      <header>
        <h1 className="text-2xl font-black text-accent">Leçons</h1>
        <p className="mt-1 text-sm text-white/60">
          Principes fondamentaux du 4mation, du débutant à l'intermédiaire.
        </p>
      </header>

      {error && <p className="text-sm text-p1">{error}</p>}

      <div className="grid gap-4 sm:grid-cols-2">
        {lessons.map((l) => (
          <Link key={l.id} to={`/learn/lessons/${l.id}`} className="group">
            <Card className="h-full transition group-hover:border-accent/50">
              <span className="text-xs font-bold uppercase text-white/40">{l.level}</span>
              <h2 className="mt-1 text-lg font-bold text-accent">{l.title}</h2>
              <p className="mt-2 text-sm text-white/60">~{l.duration_min} min</p>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
