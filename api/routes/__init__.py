"""Routes HTTP de l'API 4mation."""

from .learn import learn_bp
from .account import account_bp
from .game import game_bp
from .solver import solver_bp
from .solver_workers import solver_workers_bp

__all__ = ["account_bp", "game_bp", "learn_bp", "solver_bp", "solver_workers_bp"]
