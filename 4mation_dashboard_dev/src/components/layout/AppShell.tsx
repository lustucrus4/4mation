import { Link, Outlet } from "react-router-dom";
import NavBar from "./NavBar";

export default function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:py-8">
        <Outlet />
      </main>
      {/* pb-24 sous sm : laisse la place à la barre d'onglets fixe du bas */}
      <footer className="border-t border-white/10 px-4 pb-24 pt-6 text-center text-sm text-white/60 sm:pb-6">
        4mation — solveur exact 7×7 ·{" "}
        <Link className="inline-block py-2 hover:text-accent" to="/analyze/rl">
          Coulisses : entraînement RL
        </Link>
        {" · "}
        <a className="inline-block py-2 hover:text-accent" href="/solver.html">
          avancement du solveur
        </a>
      </footer>
    </div>
  );
}
