import { Routes, Route } from "react-router-dom";
import RulesPage from "./RulesPage";
import LearnPage from "./LearnPage";
import OpeningExplorerPage from "./OpeningExplorerPage";
import PuzzlePage from "./PuzzlePage";
import TrainerPage from "./TrainerPage";
import LessonsPage from "./LessonsPage";
import LessonDetailPage from "./LessonDetailPage";

export default function LearnRoutes() {
  return (
    <Routes>
      <Route index element={<LearnPage />} />
      <Route path="rules" element={<RulesPage />} />
      <Route path="openings" element={<OpeningExplorerPage />} />
      <Route path="puzzles" element={<PuzzlePage />} />
      <Route path="trainer" element={<TrainerPage />} />
      <Route path="lessons" element={<LessonsPage />} />
      <Route path="lessons/:lessonId" element={<LessonDetailPage />} />
    </Routes>
  );
}
