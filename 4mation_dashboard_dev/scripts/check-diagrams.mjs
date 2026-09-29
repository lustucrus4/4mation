/**
 * Relit le catalogue de schémas des pages « Apprendre » et vérifie qu'il est jouable.
 *
 * Les schémas de `src/components/learn/diagrams.ts` sont dessinés à la main : une
 * coordonnée inversée (`[col, row]` au lieu de `[row, col]`) ou une case hors plateau
 * produit un schéma plausible à l'œil mais faux. Ce script charge réellement le module
 * TypeScript et contrôle chaque schéma :
 *
 *   - plateau 7×7, cases limitées à 0/1/2 ;
 *   - clés de surbrillance et de libellé dans le plateau, styles connus ;
 *   - `last` et `win` posés sur une case occupée (un « dernier coup » ne peut pas être
 *     une case vide) ;
 *   - ligne gagnante : 4 cases alignées, occupées par le même joueur.
 *
 *   cd 4mation_dashboard_dev && npm run check:diagrams
 *
 * Aucune dépendance nouvelle : le module est chargé via `jiti`, déjà présent.
 */

import { createJiti } from "jiti";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ICI = path.dirname(fileURLToPath(import.meta.url));
const MODULE = path.resolve(ICI, "../src/components/learn/diagrams.ts");

const STYLES = ["valid", "invalid", "win", "focus", "last", "best"];
const DIRECTIONS = [
  [0, 1],
  [1, 0],
  [1, 1],
  [1, -1],
];

/** Liste des problèmes du schéma (vide = schéma valide). */
function validate(name, diagram) {
  const problemes = [];
  const { board, highlights = {}, labels = {}, winLine, caption } = diagram;

  if (!Array.isArray(board) || board.length !== 7) {
    return [`${name} : plateau absent ou de mauvaise taille`];
  }
  if (board.some((ligne) => !Array.isArray(ligne) || ligne.length !== 7)) {
    return [`${name} : le plateau n'est pas 7×7`];
  }
  if (!caption || !String(caption).trim()) problemes.push(`${name} : légende vide`);

  const dansPlateau = (cle) => {
    const parts = String(cle).split(",");
    if (parts.length !== 2) return false;
    const [row, col] = parts.map((p) => Number(p));
    return Number.isInteger(row) && Number.isInteger(col) && row >= 0 && row < 7 && col >= 0 && col < 7;
  };

  for (const [champ, valeurs] of [
    ["surbrillance", highlights],
    ["libellé", labels],
  ]) {
    for (const cle of Object.keys(valeurs)) {
      if (!dansPlateau(cle)) problemes.push(`${name} : clé de ${champ} hors plateau (${cle})`);
    }
  }
  for (const [cle, style] of Object.entries(highlights)) {
    if (!STYLES.includes(style)) problemes.push(`${name} : style inconnu ${style} en ${cle}`);
  }

  for (const style of ["last", "win"]) {
    for (const [cle, valeur] of Object.entries(highlights)) {
      if (valeur !== style || !dansPlateau(cle)) continue;
      const [row, col] = cle.split(",").map(Number);
      if (board[row][col] === 0) {
        problemes.push(`${name} : « ${style} » sur une case vide (${cle})`);
      }
    }
  }

  // Un « meilleur coup » n'a de sens que sur une case encore libre : on ne suggère pas
  // de rejouer sur un pion déjà posé. Même logique pour « jouable » et « refusée » :
  // un contour vert sur un pion, ou un ✕ sur un pion, ne décrit aucune règle.
  for (const style of ["best", "valid", "invalid"]) {
    for (const [cle, valeur] of Object.entries(highlights)) {
      if (valeur !== style || !dansPlateau(cle)) continue;
      const [row, col] = cle.split(",").map(Number);
      if (board[row][col] !== 0) {
        problemes.push(`${name} : « ${style} » sur une case déjà occupée (${cle})`);
      }
    }
  }

  for (const ligne of board) {
    for (const valeur of ligne) {
      if (![0, 1, 2].includes(valeur)) problemes.push(`${name} : case invalide (${valeur})`);
    }
  }

  if (winLine) {
    if (!Array.isArray(winLine) || winLine.length < 2) {
      problemes.push(`${name} : ligne gagnante incomplète`);
    } else {
      for (const cell of winLine) {
        if (!Array.isArray(cell) || cell.length !== 2 || !dansPlateau(cell.join(","))) {
          problemes.push(`${name} : point de ligne gagnante hors plateau (${cell})`);
        }
      }
      // Les 4 cases de l'alignement doivent exister et appartenir au même joueur.
      const [depart, arrivee] = [winLine[0], winLine[winLine.length - 1]];
      const alignement = [];
      for (let pas = 0; pas < 4; pas += 1) {
        const row = depart[0] + Math.sign(arrivee[0] - depart[0]) * pas;
        const col = depart[1] + Math.sign(arrivee[1] - depart[1]) * pas;
        alignement.push([row, col]);
      }
      const joueurs = new Set(alignement.map(([row, col]) => board[row]?.[col]));
      if (joueurs.size !== 1 || joueurs.has(0) || joueurs.has(undefined)) {
        problemes.push(
          `${name} : la ligne gagnante ${JSON.stringify(winLine)} n'est pas un alignement de 4 pions identiques`
        );
      }
      const [dr, dc] = [arrivee[0] - depart[0], arrivee[1] - depart[1]];
      if (!DIRECTIONS.some(([r, c]) => r * dc === c * dr && r * dr + c * dc > 0)) {
        problemes.push(`${name} : la ligne gagnante n'est pas droite`);
      }
    }
  }

  return problemes;
}

const jiti = createJiti(import.meta.url, { moduleCache: false });
const module = await jiti.import(MODULE);
const catalogue = Object.entries(module).filter(
  ([, valeur]) => valeur && typeof valeur === "object" && Array.isArray(valeur.board)
);

if (!catalogue.length) {
  console.error("Aucun schéma trouvé dans diagrams.ts");
  process.exit(1);
}

const problemes = catalogue.flatMap(([nom, diagram]) => validate(nom, diagram));

console.log(`${catalogue.length} schéma(s) relu(s) depuis diagrams.ts`);
for (const [nom] of catalogue) console.log(`  - ${nom}`);
if (problemes.length) {
  console.error(`\n${problemes.length} problème(s) :`);
  for (const probleme of problemes) console.error(`  ✕ ${probleme}`);
  process.exit(1);
}
console.log("\n[OK] Tous les schémas sont valides");
