import { Link } from "react-router-dom";
import Card from "../components/ui/Card";
import RuleDiagram from "../components/learn/RuleDiagram";
import {
  centerHeatmapDiagram,
  centerLinesDiagram,
  cornerFrontierDiagram,
  cornerLinesDiagram,
  drawDiagram,
  emptyBoardDiagram,
  firstMoveDiagram,
  frontierDiagram,
  frontierMidGameDiagram,
  ghostThreatDiagram,
  immediateWinDiagram,
  rescueRuleDiagram,
  threatOnFrontierDiagram,
  turnOrderDiagram,
  winAntiDiagonalDiagram,
  winDiagonalDiagram,
  winHorizontalDiagram,
  winLastMoveDiagram,
  winVerticalDiagram,
  type LearnDiagram,
} from "../components/learn/diagrams";

/** Rend un schéma du catalogue `diagrams.ts`, plein format ou compact. */
function Diagram({ diagram, compact }: { diagram: LearnDiagram; compact?: boolean }) {
  return <RuleDiagram {...diagram} compact={compact} />;
}

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
          <Diagram diagram={emptyBoardDiagram} />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">2. Objectif : aligner 4 pions</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Vous gagnez dès que <strong>4 de vos pions</strong> forment une ligne continue. Il
          existe <strong>quatre directions</strong> — les deux diagonales comptent, et beaucoup
          de débutants les oublient.
        </p>
        <div className="mt-5 grid gap-6 sm:grid-cols-2">
          <Diagram compact diagram={winHorizontalDiagram} />
          <Diagram compact diagram={winVerticalDiagram} />
          <Diagram compact diagram={winDiagonalDiagram} />
          <Diagram compact diagram={winAntiDiagonalDiagram} />
        </div>
        <p className="mt-5 text-sm leading-relaxed text-white/80">
          La victoire est immédiate : dès que la ligne est formée, la partie s'arrête, même si
          l'adversaire avait un alignement en préparation.
        </p>
        <div className="mt-4 flex justify-center">
          <Diagram diagram={winLastMoveDiagram} />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">3. Alternance des tours</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Les joueurs jouent à tour de rôle. Le rouge commence. Chaque tour, vous posez
          exactement <strong>un pion</strong> sur une case libre — les pions ne bougent plus
          jamais ensuite.
        </p>
        <div className="mt-4 flex justify-center">
          <Diagram diagram={turnOrderDiagram} />
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
          cliquer n'importe quelle case. C'est la seule fois — ensuite, tout est contraint par
          le coup précédent. Les cases en vert pointillé sont toutes légales.
        </p>
        <div className="mt-4 flex justify-center">
          <Diagram diagram={firstMoveDiagram} />
        </div>
        <p className="mt-3 text-xs text-white/50">
          En pratique, on joue presque toujours au centre : la section 9 explique pourquoi.
        </p>
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
          <Diagram diagram={frontierDiagram} />
        </div>
        <p className="mt-3 text-sm leading-relaxed text-white/80">
          Les cases marquées <span className="text-p1">✕</span> ne sont pas « mauvaises » :
          elles sont <strong>interdites</strong>, simplement parce qu'elles sont trop loin du
          dernier coup.
        </p>
        <div className="mt-5 flex justify-center">
          <Diagram compact diagram={cornerFrontierDiagram} />
        </div>
        <p className="mt-3 text-xs text-white/50">
          La largeur de la frontière dépend de l'endroit du plateau : 8 réponses possibles
          après un coup au centre, 3 seulement après un coup en coin. C'est l'une des raisons
          pour lesquelles un coup de bord vous coûte cher.
        </p>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">6. Coup valide en milieu de partie</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Ici le bleu vient de jouer en (3,4). Seules les cases qui touchent{" "}
          <strong>ce dernier coup</strong> sont légales pour le rouge. La case (3,2) touche un
          pion rouge plus ancien, mais pas le dernier coup : elle est refusée.
        </p>
        <div className="mt-4 flex justify-center">
          <Diagram diagram={frontierMidGameDiagram} />
        </div>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">7. Règle de secours</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Que faire quand les 8 voisins du dernier coup sont <strong>tous occupés</strong> ? La
          partie ne se bloque pas : vous pouvez alors jouer sur n'importe quelle case vide
          touchant un pion <strong>adverse</strong>. C'est la seule exception à la frontière —
          et elle décide de nombreuses fins de partie, car elle permet de « sauter » vers une
          ligne d'attaque restée à distance.
        </p>
        <div className="mt-4 flex justify-center">
          <Diagram diagram={rescueRuleDiagram} />
        </div>
        <p className="mt-3 text-xs text-white/50">
          Notez que la case (6,6) reste refusée : elle ne touche aucun pion bleu. La règle
          ouvre des cases, elle n'ouvre pas tout le plateau.
        </p>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">8. Menaces et blocages</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Trois pions alignés avec une 4<sup>e</sup> case libre constituent une{" "}
          <strong>menace</strong>. Mais attention : compléter la ligne ne suffit pas, il faut
          aussi que la case soit <strong>jouable</strong>. Une case qui termine un 4 mais qui
          n'est pas sur la frontière ne sert à rien — elle est inatteignable.
        </p>
        <div className="mt-4 flex justify-center">
          <Diagram diagram={threatOnFrontierDiagram} />
        </div>
        <p className="mt-3 text-sm leading-relaxed text-white/80">
          Ici, (3,4) est à la fois sur la frontière et gagnante : le bleu <strong>doit</strong>{" "}
          y répondre. (3,0) compléterait aussi la ligne, mais elle est hors frontière : le rouge
          ne pourra pas y jouer. Retenez l'ordre de priorité :{" "}
          <em>gagner tout de suite</em>, puis <em>empêcher l'adversaire de gagner</em>, puis{" "}
          <em>créer une menace</em>.
        </p>
        <div className="mt-5 grid gap-6 sm:grid-cols-2">
          <Diagram compact diagram={immediateWinDiagram} />
          <Diagram compact diagram={ghostThreatDiagram} />
        </div>
        <p className="mt-3 text-xs text-white/50">
          À gauche : un gain immédiat — la case ★ est jouable et termine l'alignement. À
          droite : trois pions alignés qui ne menacent rien du tout, parce que les deux cases
          de complétion sont hors frontière. C'est la <strong>menace fantôme</strong>, l'erreur
          de lecture la plus fréquente.
        </p>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">9. Pourquoi le centre domine</h2>
        <p className="mt-2 text-sm leading-relaxed text-white/80">
          Toutes les cases ne se valent pas. Comptons les alignements de 4 qui passent par
          chaque case : un pion central participe à beaucoup plus de lignes possibles qu'un
          pion de bord. C'est ce qui justifie le premier coup au centre.
        </p>
        <div className="mt-4 flex justify-center">
          <Diagram diagram={centerHeatmapDiagram} />
        </div>
        <div className="mt-5 grid gap-6 sm:grid-cols-2">
          <Diagram compact diagram={centerLinesDiagram} />
          <Diagram compact diagram={cornerLinesDiagram} />
        </div>
        <p className="mt-3 text-xs text-white/50">
          Un coup de coin ne peut jamais figurer dans plus de 3 alignements de 4 ; le centre,
          dans 16. Sur 7×7, cela représente presque toute votre puissance d'attaque.
        </p>
      </Card>

      <Card>
        <h2 className="text-lg font-bold text-accent">10. Fin de partie</h2>
        <ul className="mt-2 space-y-2 text-sm text-white/80">
          <li>
            <strong className="text-accent">Victoire</strong> — 4 pions alignés (section 2).
          </li>
          <li>
            <strong className="text-accent">Match nul</strong> — le plateau se remplit sans
            qu'aucun alignement de 4 n'apparaisse.
          </li>
          <li>
            <strong className="text-accent">Abandon</strong> — via le bouton dédié en partie en
            ligne ou contre l'IA.
          </li>
        </ul>
        <div className="mt-4 flex justify-center">
          <Diagram diagram={drawDiagram} />
        </div>
        <p className="mt-3 text-xs text-white/50">
          Le match nul est rare mais réel : cette position est pleine, et pourtant aucune suite
          de 4 n'existe dans aucune des quatre directions. Si vous ne voyez pas de gain, ne
          forcez pas — cherchez d'abord à bloquer.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            to="/learn/trainer"
            className="rounded-lg bg-accent/15 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/25"
          >
            S'entraîner avec indices →
          </Link>
          <Link
            to="/learn/puzzles"
            className="rounded-lg bg-accent/15 px-4 py-2 text-sm font-semibold text-accent hover:bg-accent/25"
          >
            Résoudre un puzzle →
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
