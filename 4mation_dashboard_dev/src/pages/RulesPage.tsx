import { Link } from "react-router-dom";
import Card from "../components/ui/Card";
import RuleDiagram, {
  emptyRuleBoard,
  firstMoveHighlights,
  neighborHighlights,
  withPieces,
} from "../components/learn/RuleDiagram";

const empty = emptyRuleBoard();

const winHorizontal = withPieces(empty, [
  { row: 3, col: 1, player: 1 },
  { row: 3, col: 2, player: 1 },
  { row: 3, col: 3, player: 1 },
  { row: 3, col: 4, player: 1 },
]);

const winVertical = withPieces(empty, [
  { row: 1, col: 3, player: 2 },
  { row: 2, col: 3, player: 2 },
  { row: 3, col: 3, player: 2 },
  { row: 4, col: 3, player: 2 },
]);

const winDiagonal = withPieces(empty, [
  { row: 1, col: 1, player: 1 },
  { row: 2, col: 2, player: 1 },
  { row: 3, col: 3, player: 1 },
  { row: 4, col: 4, player: 1 },
]);

const turnExample = withPieces(empty, [
  { row: 3, col: 3, player: 1 },
  { row: 3, col: 4, player: 2 },
  { row: 2, col: 3, player: 1 },
]);

const frontierBase = withPieces(empty, [{ row: 3, col: 3, player: 1 }]);
const frontierHighlights = {
  ...neighborHighlights(3, 3),
  "3,3": "last" as const,
  "1,1": "invalid" as const,
  "5,5": "invalid" as const,
};

const midGameExample = withPieces(empty, [
  { row: 3, col: 3, player: 1 },
  { row: 3, col: 4, player: 2 },
]);
const midGameHighlights = {
  ...neighborHighlights(3, 4),
  "3,4": "last" as const,
  "3,2": "invalid" as const,
  "0,0": "invalid" as const,
};

const threatExample = withPieces(empty, [
  { row: 3, col: 1, player: 1 },
  { row: 3, col: 2, player: 1 },
  { row: 3, col: 3, player: 1 },
  { row: 3, col: 4, player: 2 },
]);
const threatHighlights = {
  "3,4": "last" as const,
  "3,5": "valid" as const,
  "3,0": "focus" as const,
};

export default function RulesPage() {
  return (
    <article className="mx-auto max-w-3xl space-y-8">
      <Link to="/learn" className="text-sm text-white/50 hover:text-accent">
        ← Apprendre
      </Link>

      <header>
        <h1 className="text-2xl font-black text-accent">Règles du jeu</h1>
        <p className="mt-1 text-sm text-white/60">
          Comprendre le 4mation en quelques minutes, avec des schémas visuels.
        </p>
      </header>

      <Card>
        <h2 className="text-lg font-bold text-accent">1. Le plateau</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Le 4mation se joue sur une grille carrée de <strong>7×7 cases</strong>. Deux joueurs
          s'affrontent : le <span className="text-p1">joueur rouge</span> (1) et le{" "}
          <span className="text-p2">joueur bleu</span> (2). Les cases vides sont prêtes à
          recevoir un pion.
        </p>
        <div className="mt-4 flex justify-center">
          <RuleDiagram board={empty} caption="Plateau vide — 7 cases × 7 cases" />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">2. Objectif : aligner 4 pions</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Vous gagnez dès que <strong>4 de vos pions</strong> forment une ligne continue,
          horizontale, verticale ou diagonale. Dès qu'un alignement de 4 est formé, la partie
          s'arrête immédiatement.
        </p>
        <div className="mt-5 grid gap-6 sm:grid-cols-3">
          <RuleDiagram
            compact
            board={winHorizontal}
            winLine={[
              [3, 1],
              [3, 4],
            ]}
            highlights={{
              "3,1": "win",
              "3,2": "win",
              "3,3": "win",
              "3,4": "win",
            }}
            caption="Horizontal"
          />
          <RuleDiagram
            compact
            board={winVertical}
            winLine={[
              [1, 3],
              [4, 3],
            ]}
            highlights={{
              "1,3": "win",
              "2,3": "win",
              "3,3": "win",
              "4,3": "win",
            }}
            caption="Vertical"
          />
          <RuleDiagram
            compact
            board={winDiagonal}
            winLine={[
              [1, 1],
              [4, 4],
            ]}
            highlights={{
              "1,1": "win",
              "2,2": "win",
              "3,3": "win",
              "4,4": "win",
            }}
            caption="Diagonal"
          />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">3. Alternance des tours</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Les joueurs jouent à tour de rôle. Le rouge commence en général. Chaque tour, vous
          posez exactement <strong>un pion</strong> sur une case libre.
        </p>
        <div className="mt-4 flex justify-center">
          <RuleDiagram
            board={turnExample}
            highlights={{ "2,3": "last" }}
            caption="Rouge centre → Bleu à droite → Rouge en haut (ordre des coups)"
          />
        </div>
        <ol className="mt-4 space-y-1 text-sm text-white/70">
          <li>
            <span className="text-p1">①</span> Rouge joue au centre (3,3)
          </li>
          <li>
            <span className="text-p2">②</span> Bleu répond à côté (3,4)
          </li>
          <li>
            <span className="text-p1">③</span> Rouge se connecte par le haut (2,3)
          </li>
        </ol>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">4. Premier coup libre</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Au <strong>premier coup</strong> de la partie, le plateau est vide : vous pouvez
          cliquer n'importe quelle case. Les cases en vert pointillé sont toutes légales.
        </p>
        <div className="mt-4 flex justify-center">
          <RuleDiagram
            board={empty}
            highlights={firstMoveHighlights()}
            caption="Toutes les cases sont valides au coup 1"
          />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">5. Règle de la frontière</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          À partir du deuxième coup, vous devez poser sur l'une des{" "}
          <strong>8 cases adjacentes au dernier coup joué</strong> (horizontal, vertical ou
          diagonal). Ce n'est pas n'importe quel pion du plateau qui compte — seule la case du
          coup précédent définit la frontière.
        </p>
        <div className="mt-4 flex justify-center">
          <RuleDiagram
            board={frontierBase}
            highlights={frontierHighlights}
            caption="Dernier coup rouge (3,3) — vert = cases valides pour le bleu"
          />
        </div>
        <p className="mt-3 text-xs text-white/50">
          Si les 8 voisins du dernier coup sont tous occupés, vous pouvez alors jouer sur une
          case vide adjacente à un pion adverse (règle de secours).
        </p>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">6. Coup valide en milieu de partie</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Ici le bleu vient de jouer en (3,4) : seules les cases qui touchent{" "}
          <strong>ce dernier coup</strong> sont légales pour le rouge. La case (3,2) touche un
          pion rouge plus ancien mais pas le dernier coup — elle est refusée.
        </p>
        <div className="mt-4 flex justify-center">
          <RuleDiagram
            board={midGameExample}
            highlights={midGameHighlights}
            caption="Dernier coup bleu (3,4) — vert = légal · ✕ = hors frontière"
          />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">7. Menaces et blocages</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Trois pions alignés avec une case libre pour compléter le 4 constituent une{" "}
          <strong>menace</strong>. L'adversaire doit bloquer sur cette case s'il peut légalement y jouer.
          Priorité tactique : gagner tout de suite, bloquer une victoire adverse, puis créer une menace.
        </p>
        <div className="mt-4 flex justify-center">
          <RuleDiagram
            board={threatExample}
            highlights={threatHighlights}
            caption="Rouge menace (3,5) — bleu doit bloquer si la case est sur la frontière"
          />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">8. Fin de partie</h2>
        <ul className="mt-2 space-y-2 text-sm text-white/80">
          <li>
            <strong className="text-accent">Victoire</strong> — 4 pions alignés (voir section 2).
          </li>
          <li>
            <strong className="text-accent">Match nul</strong> — plateau rempli sans alignement de
            4 (rare sur 7×7).
          </li>
          <li>
            <strong className="text-accent">Abandon</strong> — via le bouton dédié en partie en
            ligne ou contre l'IA.
          </li>
        </ul>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            to="/learn/trainer"
            className="rounded-lg bg-accent/15 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/25"
          >
            S'entraîner avec indices →
          </Link>
          <Link
            to="/play"
            className="rounded-lg border border-white/20 px-4 py-2 text-sm font-semibold text-white/80 hover:bg-white/10"
          >
            Jouer une partie →
          </Link>
        </div>
      </Card>
    </article>
  );
}
