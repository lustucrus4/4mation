import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="py-20 text-center">
      <p className="text-6xl font-black text-accent">404</p>
      <p className="mt-3 text-white/70">Cette page n'existe pas.</p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">
        <Link
          to="/play"
          className="rounded-lg bg-accent px-6 py-3 font-bold text-deep transition hover:bg-accent-hover"
        >
          Jouer
        </Link>
        <Link
          to="/learn"
          className="rounded-lg border border-accent px-6 py-3 font-bold text-accent transition hover:bg-accent/10"
        >
          Apprendre
        </Link>
      </div>
      <Link to="/" className="mt-6 inline-block py-2 text-sm text-white/60 hover:text-accent">
        Retour à l'accueil
      </Link>
    </div>
  );
}
