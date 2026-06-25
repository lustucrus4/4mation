import { Routes, Route, Link, useLocation } from "react-router-dom";
import PlayPage from "./PlayPage";
import OnlinePlayPage from "./OnlinePlayPage";

function PlayNav() {
  const { pathname } = useLocation();
  const isOnline = pathname.includes("/play/online");

  return (
    <nav className="mb-6 flex gap-2 rounded-xl border border-white/10 bg-white/5 p-1">
      <Link
        to="/play"
        className={[
          "flex-1 rounded-lg px-4 py-2 text-center text-sm font-semibold transition",
          !isOnline ? "bg-accent text-deep" : "text-white/70 hover:text-white",
        ].join(" ")}
      >
        vs IA
      </Link>
      <Link
        to="/play/online"
        className={[
          "flex-1 rounded-lg px-4 py-2 text-center text-sm font-semibold transition",
          isOnline ? "bg-accent text-deep" : "text-white/70 hover:text-white",
        ].join(" ")}
      >
        En ligne
      </Link>
    </nav>
  );
}

export default function PlayRoutes() {
  return (
    <div>
      <PlayNav />
      <Routes>
        <Route index element={<PlayPage />} />
        <Route path="online" element={<OnlinePlayPage />} />
      </Routes>
    </div>
  );
}
