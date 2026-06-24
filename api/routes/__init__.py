"""Routes HTTP de l'API 4mation."""

from .game import game_bp
from .solver import solver_bp
from .solver_workers import solver_workers_bp

__all__ = ["game_bp", "solver_bp", "solver_workers_bp"]
