"""Compatibility module for JARVIS role-based model routing."""
from .core_router import RoleDecision, RoleRouterProvider, classify_role

__all__ = ["RoleDecision", "RoleRouterProvider", "classify_role"]
