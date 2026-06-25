import { Routes, Route } from "react-router-dom";
import AnalyzePage from "./AnalyzePage";
import GameReviewPage from "./GameReviewPage";

/** Routes Analyser : liste + revue détaillée par partie. */
export default function AnalyzeRoutes() {
  return (
    <Routes>
      <Route index element={<AnalyzePage />} />
      <Route path=":gameId" element={<GameReviewPage />} />
    </Routes>
  );
}
