# Entraînement IA par RL — 4mation

> **Pour Lucien** — tu n’as rien à configurer. Une commande lance l’entraînement, le dashboard suit la progression, une autre commande teste l’IA contre le niveau 5.

## En bref : c’est quoi le RL ici ?

1. **Phase 1 (nouveau)** : l’IA s’entraîne **uniquement contre level_5** (Minimax expert Python) jusqu’à **≥50 % de victoires** en éval.
2. **Phase 2** : bascule automatique vers le **self-play** (AlphaZero-lite + MCTS + curriculum) une fois le seuil atteint.
3. Après chaque batch, elle **ajuste ses poids** (REINFORCE + tête value).
4. Tous les **10 000 parties**, test vs **level_5** ; tous les **25 000 parties**, test vs **level_3** (dans les deux phases).
5. Les résultats sont visibles sur **`/analyze/rl`** dans le dashboard local.

**Langages :** moteur de jeu et entraînement en **Rust** (rapide). Le bot niveau 5 reste en **Python** uniquement pour l’évaluation et la phase 1 (référence existante du site).

## Commandes (depuis `4mation/`)

```powershell
# Lancer / relancer l'entraînement (16 cœurs, arrière-plan)
# Par défaut : phase auto (L5 puis self-play)
.\scripts\rl.ps1 train

# Reprendre le dernier checkpoint (conserve le réseau entraîné)
.\scripts\rl.ps1 train -Resume

# Forcer la phase 1 uniquement (pas de bascule auto)
.\scripts\rl.ps1 train -Fresh -TrainingPhase vs_level5

# Ajuster le seuil de bascule (défaut 50 %)
.\scripts\rl.ps1 train -Fresh -Phase2WinThreshold 0.45 -PhaseTransitionGames 20

# Sauter la phase 1 (self-play direct, comportement v3)
.\scripts\rl.ps1 train -TrainingPhase self_play

# Tuning perf (exemples)
.\scripts\rl.ps1 train -Resume -MctsSims 40 -EvalEveryL5 15000 -SelfPlayGames 1200

# Voir l'état + dernières lignes de log
.\scripts\rl.ps1 status

# Tester le checkpoint actuel vs niveau 5 (12 parties par défaut)
.\scripts\rl.ps1 eval

# Arrêter l'entraînement
.\scripts\rl.ps1 stop
```

> **Important :** si un `train.exe` tourne déjà (PID dans `status.json`), arrête-le avant de recompiler :
> `.\scripts\rl.ps1 stop` puis relance `train`. Sinon `cargo build` peut échouer (fichier verrouillé sous Windows).

**Dashboard local :** API `py api/app.py` + front `npm run dev` dans `4mation_dashboard_dev` → page `/analyze/rl`.

## Fichiers importants

| Fichier | Rôle |
|---------|------|
| `script/rl_rust/` | Code Rust (self-play, policy, MCTS) |
| `script/rl_rust/data/status.json` | État live (`training_phase`, métriques) |
| `script/rl_rust/data/checkpoints/latest.json` | Dernier modèle |
| `script/rl_rust/data/metrics.jsonl` | Historique métriques (`vs_level5`, `self_play`, `phase_transition`) |
| `script/solver_rust/` | Règles du jeu (plateau 7×7, alignement 4) |

## Objectif

Faire monter le **win rate vs level_5**. La v1 (policy linéaire) a plafonné après 16M parties (0 victoire, nulles uniquement).

## v3.2 — Phase L5 puis self-play (actif)

### Stratégie en deux phases

| Phase | Mode | Description |
|-------|------|-------------|
| **1** | `vs_level5` | Parties d'entraînement **100 % vs level_5** (daemon Python), updates policy |
| **2** | `self_play` | Self-play + curriculum (comportement v3 inchangé) |

**Bascule auto** (`--training-phase auto`, défaut) : quand l'éval périodique vs level_5 atteint **≥ `--phase2-win-threshold`** (défaut 0,50) sur **`--phase-transition-games`** parties (défaut 20), événement `phase_transition` dans `metrics.jsonl` et passage en self-play.

- **Évals L3/L5** : inchangées, dans les deux phases.
- **Reprise** (`-Resume`) sans champ `training_phase` : reste en self-play (runs existants).
- **Fresh** (`-Fresh`) : repart phase 1 si mode `auto`.

### Risques phase 1

- Level_5 est **très fort** : la phase 1 peut être **lente** (coups Python + MCTS) et **instable** au début (beaucoup de défaites).
- Estimation grossière : **plusieurs heures à jours** selon le réseau, avant d'atteindre 50 % (dépend fortement du bootstrap).
- Variante si trop lent : entraîner d'abord vs level_3 (`-TrainingPhase vs_level5` avec seuil abaissé, ou curriculum Rust en attendant) — non activée par défaut.

### Paramètres perf (défauts v3.2, tunables via CLI)

| Paramètre | Défaut | Rôle |
|-----------|--------|------|
| `--training-phase` | `auto` | `auto` \| `vs_level5` \| `self_play` |
| `--phase2-win-threshold` | `0.50` | Seuil win rate L5 pour phase 2 |
| `--phase-transition-games` | `20` | Parties eval L5 pour décision stable |
| `--self-play-games` | 1200 | Batch par step (rayon) |
| `--mcts-sims` | 36 | Simulations MCTS self-play |
| `--eval-mcts-sims` | 16 | MCTS léger en eval (vs 96 avant) |
| `--eval-every-l5` | 10000 | Fréquence eval level_5 |
| `--eval-every-l3` | 25000 | Fréquence eval level_3 |
| `--eval-games` | 12 | Parties par eval (phase 2 ; phase 1 auto utilise max(12, transition)) |
| `--checkpoint-every` | 25 | Checkpoint numéroté (latest à chaque step) |

Gain attendu phase 2 : **~1,5–2× games/sec effectifs** (moins d'I/O checkpoint, eval espacée/allégée, MCTS plus rapide).

```powershell
.\scripts\rl.ps1 train -Fresh
```

## Option avancée (bootstrap lent)

Par défaut : bootstrap **heuristique Rust** (~3 s). Pour imiter le Minimax Python au démarrage (plus lent) :

```powershell
.\scripts\rl.ps1 train -Imitate
```

## Ne plus utiliser

- Lancer `cargo` depuis `Projet code` (sans `cd 4mation/script/rl_rust`) → erreur `Cargo.toml`.
- L’ancien pipeline Python PPO (`script/train.py`) — remplacé par Rust pour la perf.
- Dossier dupliqué `script/rl_rust/script/rl_rust/data/` — ignoré ; tout doit aller dans `script/rl_rust/data/`.
