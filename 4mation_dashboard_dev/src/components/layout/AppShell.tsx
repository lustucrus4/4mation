import { Outlet } from "react-router-dom";
import NavBar from "./NavBar";

export default function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <footer className="border-t border-white/10 px-4 py-6 text-center text-sm text-white/50">
        4mation — solveur exact 7×7 ·{" "}
        <a className="hover:text-accent" href="/solver.html">
          Avancement solveur
        </a>
      </footer>
    </div>
  );
}
