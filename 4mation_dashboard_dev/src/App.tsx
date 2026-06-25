import { Routes, Route } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import HomePage from "./pages/HomePage";
import PlayRoutes from "./pages/PlayRoutes";
import LearnRoutes from "./pages/LearnRoutes";
import AnalyzeRoutes from "./pages/AnalyzeRoutes";
import ProfilePage from "./pages/ProfilePage";
import NotFoundPage from "./pages/NotFoundPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="play/*" element={<PlayRoutes />} />
        <Route path="learn/*" element={<LearnRoutes />} />
        <Route path="analyze/*" element={<AnalyzeRoutes />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
