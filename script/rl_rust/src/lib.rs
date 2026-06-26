pub mod eval;
pub mod features;
pub mod game_session;
pub mod imitation;
pub mod mcts;
pub mod persistence;
pub mod policy;
pub mod self_play;
pub mod trainer;

pub use policy::LinearPolicy;
pub use trainer::{TrainConfig, Trainer};
