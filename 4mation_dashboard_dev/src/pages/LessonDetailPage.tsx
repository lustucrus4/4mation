import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import LessonBody from "../components/learn/LessonBody";
import RuleDiagram, { type CellValue } from "../components/learn/RuleDiagram";
import Card from "../components/ui/Card";
import { fetchLesson, fetchLessons, type Lesson } from "../lib/learnApi";

export default function LessonDetailPage() {
  const { lessonId } = useParams<{ lessonId: string }>();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [next, setNext] = useState<Lesson | null>(null);

  useEffect(() => {
    if (!lessonId) return;
    setNext(null);
    fetchLessons()
      .then((all) => {
        const i = all.findIndex((l) => l.id === lessonId);
        setNext(i >= 0 && i + 1 < all.length ? all[i + 1] : null);
      })
      .catch(() => setNext(null));
  }, [lessonId]);

  useEffect(() => {
    if (!lessonId) return;
    fetchLesson(lessonId)
      .then(setLesson)
      .catch((err) => setError(err instanceof Error ? err.message : "Erreur"));
  }, [lessonId]);

  if (error) {
    return (
      <div className="space-y-4">
        <Link to="/learn/lessons" className="inline-block py-2 text-sm text-white/60 hover:text-accent">
          ← Leçons
        </Link>
        <p className="text-p1">{error}</p>
      </div>
    );
  }

  if (!lesson) {
    return <p className="text-white/60">Chargement…</p>;
  }

  return (
    <article className="mx-auto max-w-2xl space-y-6">
      <Link to="/learn/lessons" className="inline-block py-2 text-sm text-white/60 hover:text-accent">
        ← Leçons
      </Link>
      <header>
        <span className="text-xs font-bold uppercase text-white/60">{lesson.level}</span>
        <h1 className="mt-1 text-3xl font-black text-accent">{lesson.title}</h1>
        <p className="mt-1 text-sm text-white/60">~{lesson.duration_min} min de lecture</p>
      </header>

      {lesson.sections.map((s) => (
        <Card key={s.heading}>
          <h2 className="text-lg font-bold text-accent">{s.heading}</h2>
          <LessonBody body={s.body} />
          {s.diagram && (
            <div className="mt-4">
              <RuleDiagram
                board={s.diagram.board as CellValue[][]}
                highlights={s.diagram.highlights}
                labels={s.diagram.labels}
                winLine={s.diagram.win_line}
                caption={s.diagram.caption}
              />
            </div>
          )}
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

      <nav className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-6">
        <Link to="/learn/lessons" className="py-2 text-sm text-white/60 hover:text-accent">
          ← Toutes les leçons
        </Link>
        {next && (
          <Link
            to={`/learn/lessons/${next.id}`}
            className="rounded-lg bg-accent px-4 py-2.5 text-sm font-bold text-deep transition hover:bg-accent-hover"
          >
            Leçon suivante : {next.title} →
          </Link>
        )}
      </nav>
    </article>
  );
}
