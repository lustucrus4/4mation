//! Détection et contrôle du processus solveur (Windows).

use anyhow::{Context, Result};
use std::path::{Path, PathBuf};

pub const SOLVER_PROCESS_NAME: &str = "4mation-local.exe";

pub fn is_solver_running() -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use std::process::Command;

        const CREATE_NO_WINDOW: u32 = 0x08000000;

        let output = Command::new("tasklist")
            .args(["/FI", &format!("IMAGENAME eq {SOLVER_PROCESS_NAME}"), "/NH"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();

        match output {
            Ok(out) => {
                let text = String::from_utf8_lossy(&out.stdout).to_lowercase();
                text.contains(&SOLVER_PROCESS_NAME.to_lowercase())
                    && !text.contains("aucune tâche")
                    && !text.contains("no tasks")
            }
            Err(_) => false,
        }
    }
    #[cfg(not(windows))]
    {
        false
    }
}

pub fn stop_solver_process() -> bool {
    if !is_solver_running() {
        return false;
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use std::process::Command;

        const CREATE_NO_WINDOW: u32 = 0x08000000;
        let _ = Command::new("taskkill")
            .args(["/IM", SOLVER_PROCESS_NAME, "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
        true
    }
    #[cfg(not(windows))]
    {
        false
    }
}

fn project_root() -> PathBuf {
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join("scripts").is_dir() {
            return cwd;
        }
    }
    PathBuf::from(".")
}

fn allowed_script(key: &str) -> Option<PathBuf> {
    let root = project_root();
    let path = match key {
        "solver" => root.join("scripts").join("run_local_solver_rust.bat"),
        "stack" => root.join("scripts").join("run_local_solver_stack.bat"),
        _ => return None,
    };
    let scripts = root.join("scripts");
    if !path.is_file() {
        return None;
    }
    if path.canonicalize().ok()?.starts_with(scripts.canonicalize().ok()?) {
        Some(path)
    } else {
        None
    }
}

pub fn launch_local_script(script_key: &str, window_title: &str) -> Result<PathBuf> {
    let bat_path = allowed_script(script_key).context("script inconnu ou chemin non autorisé")?;

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use std::process::Command;

        const CREATE_NEW_CONSOLE: u32 = 0x00000010;
        let cmd_line = format!("title {window_title} & call \"{}\"", bat_path.display());
        Command::new("cmd.exe")
            .args(["/k", &cmd_line])
            .current_dir(project_root())
            .creation_flags(CREATE_NEW_CONSOLE)
            .spawn()
            .context("échec lancement script")?;
    }

    #[cfg(not(windows))]
    {
        anyhow::bail!("lancement de scripts locaux réservé à Windows");
    }

    Ok(bat_path)
}
