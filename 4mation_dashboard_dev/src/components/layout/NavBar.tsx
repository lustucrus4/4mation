import { NavLink, Link } from "react-router-dom";
import AuthButton from "../auth/AuthButton";

const links = [
  { to: "/play", label: "Jouer", icon: "♟️" },
  { to: "/learn", label: "Apprendre", icon: "🎓" },
  { to: "/analyze", label: "Analyser", icon: "🔎" },
  { to: "/profile", label: "Profil", icon: "👤" },
];

function linkClass({ isActive }: { isActive: boolean }) {
  return [
    "rounded-lg px-3 py-2 text-sm font-semibold transition-colors",
    isActive ? "bg-accent/15 text-accent" : "text-white/70 hover:text-white hover:bg-white/5",
  ].join(" ");
}

function tabClass({ isActive }: { isActive: boolean }) {
  return [
    "flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-[0.7rem] font-semibold transition-colors",
    isActive ? "text-accent" : "text-white/60 hover:text-white",
  ].join(" ");
}

/**
 * Navigation principale.
 * - ≥ sm : barre unique en haut (logo, rubriques, compte).
 * - < sm : logo + compte en haut, rubriques dans une barre d'onglets fixe en bas
 *   (la barre unique ne tenait pas dans un écran de téléphone).
 */
export default function NavBar() {
  return (
    <>
      <header className="sticky top-0 z-30 border-b border-white/10 bg-night/80 backdrop-blur">
        <nav
          className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3"
          aria-label="Navigation principale"
        >
          <Link to="/" className="mr-2 flex shrink-0 items-center gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent font-black text-deep">
              4
            </span>
            <span className="text-lg font-black tracking-tight text-accent drop-shadow-[0_0_10px_rgba(17,241,204,0.4)]">
              4mation
            </span>
          </Link>

          <div className="hidden items-center gap-1 sm:flex">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} className={linkClass}>
                {l.label}
              </NavLink>
            ))}
          </div>

          <div className="ml-auto min-w-0">
            <AuthButton />
          </div>
        </nav>
      </header>

      <nav
        className="fixed inset-x-0 bottom-0 z-30 flex border-t border-white/10 bg-night/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
        aria-label="Rubriques"
      >
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} className={tabClass}>
            <span className="text-lg leading-none" aria-hidden="true">
              {l.icon}
            </span>
            {l.label}
          </NavLink>
        ))}
      </nav>
    </>
  );
}
