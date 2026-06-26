import { Routes, Route } from "react-router-dom";
import AnalyzePage from "./AnalyzePage";
import GameReviewPage from "./GameReviewPage";
import RlTrainingPage from "./RlTrainingPage";

/** Routes Analyser : liste + revue détaillée par partie. */
export default function AnalyzeRoutes() {
  return (
    <Routes>
      <Route index element={<AnalyzePage />} />
      <Route path="rl" element={<RlTrainingPage />} />
      <Route path=":gameId" element={<GameReviewPage />} />
    </Routes>
  );
}
