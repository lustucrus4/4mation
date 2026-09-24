//! `4mation-engine` — moteur de jeu et d'analyse.
//!
//! Deux modes :
//!
//! - **stdin/stdout** (défaut) : une requête JSON par ligne, une réponse JSON
//!   par ligne. C'est l'interface utilisée par l'API du site : le processus est
//!   lancé une fois et garde sa table de transposition entre les requêtes.
//! - **`--bench`** : mesure le débit de recherche.
//!
//! Requête :
//! ```json
//! {"board": [[0,0,0,0,0,0,0], ...], "current_player": 1, "last_move": [3,3], "depth": 16, "time_ms": 1000}
//! ```
//! `last_move` vaut `null` au premier coup. `depth` et `time_ms` sont optionnels.
//!
//! `"exact": true` force la recherche de chaque coup de la racine en fenêtre pleine :
//! les scores de TOUS les coups deviennent exacts, au prix d'une recherche plus lente.
//! C'est ce qu'il faut pour analyser une partie (comparer les coups entre eux), alors
//! qu'un bot qui joue seulement son meilleur coup s'en passe. Le réglage est
//! **par requête** — un même processus sert donc le bot (rapide) et l'analyse (exacte)
//! en partageant sa table de transposition. `--exact` reste le défaut du processus.
//!
//! `"all_moves": true` énumère **tous** les coups légaux à la racine au lieu des seules
//! orbites de symétrie : sans lui, le premier coup ne rend que 10 coups sur 49. Vaut
//! `exact` par défaut — un mode analyse veut les deux ensemble.
//!
//! Si la recherche est interrompue par le temps, les scores rendus sont ceux de la
//! dernière profondeur **terminée** : la liste reste complète et cohérente.

use std::io::{BufRead, Write};
use std::path::PathBuf;

use clap::Parser;
use serde_json::{json, Value};

use formation_worker::engine::{Engine, EngineConfig, MATE_MARGIN};
use formation_worker::proof::move_mask;
use formation_worker::tb_probe::SqliteProbe;

const N: i64 = 7;
const NO_LAST: u8 = 255;

#[derive(Parser, Debug)]
#[command(about = "Moteur 4mation : meilleur coup et analyse (JSON sur stdin/stdout)")]
struct Args {
    #[arg(long, default_value_t = 128)]
    tt_mb: usize,
    #[arg(long, default_value_t = 16)]
    depth: i16,
    #[arg(long, default_value_t = 1000)]
    time_ms: u64,
    /// Tablebase SQLite pour les finales exactes.
    #[arg(long)]
    tb: Option<PathBuf>,
    /// Nombre de cases vides en dessous duquel la tablebase est consultée.
    #[arg(long, default_value_t = 12)]
    tb_empty: usize,
    /// Mesure le débit de recherche puis quitte.
    #[arg(long)]
    bench: Option<u32>,
    /// Recherche chaque coup de la racine en fenêtre pleine : scores exacts
    /// pour tous les coups (plus lent, indispensable à l'analyse).
    #[arg(long)]
    exact: bool,
}

#[derive(Clone, Copy)]
struct Defaults {
    depth: i16,
    time_ms: u64,
    exact: bool,
}

fn parse_board(v: &Value) -> Option<(u64, u64)> {
    let rows = v.as_array()?;
    if rows.len() != N as usize {
        return None;
    }
    let mut p1 = 0u64;
    let mut p2 = 0u64;
    for (r, row) in rows.iter().enumerate() {
        let cells = row.as_array()?;
        if cells.len() != N as usize {
            return None;
        }
        for (c, cell) in cells.iter().enumerate() {
            let bit = 1u64 << (r * N as usize + c);
            match cell.as_i64().unwrap_or(0) {
                1 => p1 |= bit,
                2 => p2 |= bit,
                _ => {}
            }
        }
    }
    Some((p1, p2))
}

fn parse_last(v: &Value) -> u8 {
    let Some(a) = v.as_array() else {
        return NO_LAST;
    };
    if a.len() != 2 {
        return NO_LAST;
    }
    let (Some(r), Some(c)) = (a[0].as_i64(), a[1].as_i64()) else {
        return NO_LAST;
    };
    if !(0..N).contains(&r) || !(0..N).contains(&c) {
        return NO_LAST;
    }
    (r * N + c) as u8
}

fn label(score: i32) -> &'static str {
    if score >= MATE_MARGIN {
        "gain"
    } else if score <= -MATE_MARGIN {
        "perte"
    } else {
        "estimation"
    }
}

fn wdl_label(v: i8) -> &'static str {
    match v {
        1 => "gain",
        -1 => "perte",
        _ => "nulle",
    }
}

fn handle(engine: &mut Engine, req: &Value, defaults: Defaults) -> Value {
    let Some(board) = req.get("board") else {
        return json!({"error": "champ board manquant"});
    };
    let Some((p1, p2)) = parse_board(board) else {
        return json!({"error": "board invalide : 7 lignes de 7 entiers (0 vide, 1 joueur 1, 2 joueur 2)"});
    };
    let side = req
        .get("current_player")
        .and_then(|v| v.as_u64())
        .unwrap_or(1)
        .clamp(1, 2) as u8;
    let last = parse_last(req.get("last_move").unwrap_or(&Value::Null));

    let depth = req
        .get("depth")
        .and_then(|v| v.as_i64())
        .unwrap_or(defaults.depth as i64)
        .clamp(1, 60) as i16;
    let time_ms = req
        .get("time_ms")
        .and_then(|v| v.as_u64())
        .unwrap_or(defaults.time_ms);
    let exact_root = req
        .get("exact")
        .and_then(|v| v.as_bool())
        .unwrap_or(defaults.exact);
    let all_moves = req
        .get("all_moves")
        .and_then(|v| v.as_bool())
        .unwrap_or(exact_root);
    engine.set_limits(depth, time_ms);
    engine.set_exact_root(exact_root);
    engine.set_all_root_moves(all_moves);

    let r = engine.search(p1, p2, side, last);
    let mut moves: Vec<Value> = r
        .moves
        .iter()
        .map(|m| {
            json!({
                "row": m.mv as i64 / N,
                "col": m.mv as i64 % N,
                "score": m.score,
                "exact": m.exact,
                "proven": label(m.score),
            })
        })
        .collect();
    moves.sort_by(|a, b| {
        b["score"]
            .as_i64()
            .unwrap_or(0)
            .cmp(&a["score"].as_i64().unwrap_or(0))
    });

    // Le nombre de coups légaux, indépendant de la réduction par symétrie : une
    // interface d'analyse doit pouvoir dire « 12 coups affichés sur 49 ».
    let valid_moves = move_mask(p1, p2, side, last).count_ones();

    json!({
        "best_move": r.best.map(|m| json!([m as i64 / N, m as i64 % N])),
        "score": r.score,
        "proven": r.wdl().map(wdl_label).unwrap_or("aucune preuve"),
        "tb_exact": r.proven(),
        "mate_in": r.mate_in(),
        "depth": r.depth,
        "nodes": r.nodes,
        "elapsed_ms": r.elapsed.as_millis() as u64,
        "truncated": r.truncated,
        "exact_root": exact_root,
        "all_moves": all_moves,
        "valid_moves_count": valid_moves,
        "tb_skips": engine.skips(),
        "moves": moves,
    })
}

fn serve(engine: &mut Engine, defaults: Defaults) {
    let stdin = std::io::stdin();
    let mut out = std::io::stdout();
    for line in stdin.lock().lines() {
        let Ok(line) = line else { break };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let req: Value = match serde_json::from_str(line) {
            Ok(v) => v,
            Err(e) => {
                let _ = writeln!(out, "{}", json!({"error": format!("json invalide : {e}")}));
                let _ = out.flush();
                continue;
            }
        };
        if req.get("type").and_then(|t| t.as_str()) == Some("quit") {
            break;
        }
        let resp = handle(engine, &req, defaults);
        let _ = writeln!(out, "{resp}");
        let _ = out.flush();
    }
}

fn bench(engine: &mut Engine, rounds: u32) {
    // Position de milieu de partie plausible : les deux joueurs ont bâti une
    // diagonale, la recherche doit trier les menaces.
    let p1: u64 = (1u64 << 24) | (1u64 << 17) | (1u64 << 32) | (1u64 << 9);
    let p2: u64 = (1u64 << 25) | (1u64 << 18) | (1u64 << 31) | (1u64 << 10);
    let last = 17u8;
    let mut total_nodes = 0u64;
    let mut total_ms = 0u128;
    let mut best_depth = 0i16;
    for i in 0..rounds.max(1) {
        let r = engine.search(p1, p2, 1, last);
        total_nodes += r.nodes;
        total_ms += r.elapsed.as_millis();
        best_depth = best_depth.max(r.depth);
        let nps = if r.elapsed.as_secs_f64() > 0.0 {
            r.nodes as f64 / r.elapsed.as_secs_f64() / 1e6
        } else {
            0.0
        };
        println!(
            "essai {} : profondeur {} — {} nœuds — {:.0} ms — {:.2} M nœuds/s — {}",
            i + 1,
            r.depth,
            r.nodes,
            r.elapsed.as_millis(),
            nps,
            label(r.score)
        );
        // La table de transposition est conservée : les essais suivants sont
        // donc plus rapides. C'est le comportement réel d'un bot qui enchaîne
        // les coups d'une même partie.
    }
    let secs = total_ms as f64 / 1000.0;
    println!(
        "total : {} nœuds en {:.0} ms — {:.2} M nœuds/s — profondeur max {}",
        total_nodes,
        total_ms,
        if secs > 0.0 {
            total_nodes as f64 / secs / 1e6
        } else {
            0.0
        },
        best_depth
    );
}

fn main() {
    let args = Args::parse();
    let mut engine = Engine::new(EngineConfig {
        tt_mb: args.tt_mb,
        max_depth: args.depth,
        time_ms: args.time_ms,
    });
    if let Some(path) = &args.tb {
        match SqliteProbe::open(path) {
            Ok(probe) => {
                eprintln!(
                    "tablebase : {} — finales exactes jusqu'à {} cases vides",
                    path.display(),
                    args.tb_empty
                );
                engine.set_probe(Box::new(probe), args.tb_empty);
            }
            Err(e) => eprintln!("tablebase illisible ({e}) — recherche seule"),
        }
    }
    let defaults = Defaults {
        depth: args.depth,
        time_ms: args.time_ms,
        exact: args.exact,
    };
    engine.set_exact_root(args.exact);
    if let Some(rounds) = args.bench {
        bench(&mut engine, rounds);
        return;
    }
    serve(&mut engine, defaults);
}
