import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Card from "../components/ui/Card";
import { fetchLesson, type Lesson } from "../lib/learnApi";

export default function LessonDetailPage() {
  const { lessonId } = useParams<{ lessonId: string }>();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!lessonId) return;
    fetchLesson(lessonId)
      .then(setLesson)
      .catch((err) => setError(err instanceof Error ? err.message : "Erreur"));
  }, [lessonId]);

  if (error) {
    return (
      <div className="space-y-4">
        <Link to="/learn/lessons" className="text-sm text-white/50 hover:text-accent">
          ← Leçons
        </Link>
        <p className="text-p1">{error}</p>
      </div>
    );
  }

  if (!lesson) {
    return <p className="text-white/50">Chargement…</p>;
  }

  return (
    <article className="mx-auto max-w-2xl space-y-6">
      <Link to="/learn/lessons" className="text-sm text-white/50 hover:text-accent">
        ← Leçons
      </Link>
      <header>
        <span className="text-xs font-bold uppercase text-white/40">{lesson.level}</span>
        <h1 className="mt-1 text-3xl font-black text-accent">{lesson.title}</h1>
        <p className="mt-1 text-sm text-white/60">~{lesson.duration_min} min de lecture</p>
      </header>

      {lesson.sections.map((s) => (
        <Card key={s.heading}>
          <h2 className="text-lg font-bold text-accent">{s.heading}</h2>
          <p className="mt-2 leading-relaxed text-white/80">{s.body}</p>
        </Card>
      ))}

      {lesson.id === "intro" && (
        <Link
          to="/learn/rules"
          className="inline-block rounded-lg bg-accent/15 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/25"
        >
          Voir les règles illustrées →
        </Link>
      )}

      {lesson.id === "ouvertures" && (
        <Link
          to="/learn/openings"
          className="inline-block rounded-lg bg-accent/15 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/25"
        >
          Ouvrir l'explorateur d'ouvertures →
        </Link>
      )}

      {lesson.id === "lire-coach" && (
        <Link
          to="/learn/trainer"
          className="inline-block rounded-lg bg-accent/15 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/25"
        >
          Lancer l'entraîneur →
        </Link>
      )}

      {lesson.id === "menaces" && (
        <Link
          to="/learn/rules"
          className="inline-block rounded-lg bg-accent/15 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/25"
        >
          Voir les menaces illustrées →
        </Link>
      )}
    </article>
  );
}
