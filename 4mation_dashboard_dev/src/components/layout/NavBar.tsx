import { NavLink, Link } from "react-router-dom";
import AuthButton from "../auth/AuthButton";

const links = [
  { to: "/play", label: "Jouer" },
  { to: "/learn", label: "Apprendre" },
  { to: "/analyze", label: "Analyser" },
  { to: "/profile", label: "Profil" },
];

function linkClass({ isActive }: { isActive: boolean }) {
  return [
    "rounded-lg px-3 py-2 text-sm font-semibold transition-colors",
    isActive ? "bg-accent/15 text-accent" : "text-white/70 hover:text-white hover:bg-white/5",
  ].join(" ");
}

export default function NavBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-night/80 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3">
        <Link to="/" className="mr-2 flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent font-black text-deep">
            4
          </span>
          <span className="text-lg font-black tracking-tight text-accent drop-shadow-[0_0_10px_rgba(17,241,204,0.4)]">
            4mation
          </span>
        </Link>

        <div className="flex items-center gap-1">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={linkClass}>
              {l.label}
            </NavLink>
          ))}
        </div>

        <div className="ml-auto">
          <AuthButton />
        </div>
      </nav>
    </header>
  );
}
