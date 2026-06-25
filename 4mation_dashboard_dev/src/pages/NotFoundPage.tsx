import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="py-20 text-center">
      <p className="text-6xl font-black text-accent">404</p>
      <p className="mt-3 text-white/70">Cette page n'existe pas.</p>
      <Link to="/" className="mt-6 inline-block text-accent hover:underline">
        Retour à l'accueil
      </Link>
    </div>
  );
}
