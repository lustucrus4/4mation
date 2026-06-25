import { Link } from "react-router-dom";
import Card from "../components/ui/Card";

interface LearnMaintenancePageProps {
  title: string;
}

/** Section Apprendre temporairement indisponible. */
export default function LearnMaintenancePage({ title }: LearnMaintenancePageProps) {
  return (
    <div className="mx-auto max-w-lg space-y-6">
      <Link to="/learn" className="text-sm text-white/50 hover:text-accent">
        ← Apprendre
      </Link>

      <Card className="text-center">
        <p className="text-4xl" aria-hidden>
          🚧
        </p>
        <h1 className="mt-3 text-2xl font-black text-accent">{title}</h1>
        <p className="mt-2 inline-block rounded-full bg-warn/15 px-3 py-1 text-xs font-bold uppercase tracking-wide text-warn">
          En cours de développement
        </p>
        <p className="mt-4 text-sm leading-relaxed text-white/70">
          Cette section arrive bientôt. En attendant, consultez les règles illustrées ou
          entraînez-vous avec le coach.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link
            to="/learn/rules"
            className="rounded-lg bg-accent/15 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/25"
          >
            Règles illustrées
          </Link>
          <Link
            to="/learn/trainer"
            className="rounded-lg border border-white/20 px-4 py-2 text-sm font-semibold text-white/80 hover:bg-white/10"
          >
            Entraîneur
          </Link>
        </div>
      </Card>
    </div>
  );
}
