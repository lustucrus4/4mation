"""Routes HTTP de l'API 4mation."""

from .game import game_bp
from .solver import solver_bp

__all__ = ["game_bp", "solver_bp"]
