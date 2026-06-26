//! Contrôle pause / reprise du moteur solveur intégré au dashboard.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

#[derive(Clone)]
pub struct EngineControl {
    pub shutdown: Arc<AtomicBool>,
    running: Arc<AtomicBool>,
    restart: Arc<AtomicBool>,
}

impl EngineControl {
    pub fn new() -> Self {
        Self {
            shutdown: Arc::new(AtomicBool::new(false)),
            running: Arc::new(AtomicBool::new(false)),
            restart: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::Relaxed)
    }

    pub fn set_running(&self, value: bool) {
        self.running.store(value, Ordering::Relaxed);
    }

    pub fn request_stop(&self) {
        self.shutdown.store(true, Ordering::Relaxed);
    }

    /// Demande un redémarrage si le moteur est en pause.
    pub fn request_start(&self) -> bool {
        if self.is_running() {
            return false;
        }
        self.shutdown.store(false, Ordering::Relaxed);
        self.restart.store(true, Ordering::Relaxed);
        true
    }

    pub fn take_restart(&self) -> bool {
        self.restart
            .compare_exchange(true, false, Ordering::Relaxed, Ordering::Relaxed)
            .is_ok()
    }

    pub fn wait_restart(&self) {
        while !self.restart.load(Ordering::Relaxed) {
            std::thread::sleep(std::time::Duration::from_millis(200));
        }
        self.restart.store(false, Ordering::Relaxed);
    }
}

/// Signal partagé dashboard ↔ build livre d'ouverture (thread principal bloqué).
#[derive(Clone, Debug, Default)]
pub struct BuildControl {
    active: Arc<AtomicBool>,
}

impl BuildControl {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set_active(&self, value: bool) {
        self.active.store(value, Ordering::Relaxed);
    }

    pub fn is_active(&self) -> bool {
        self.active.load(Ordering::Relaxed)
    }
}
