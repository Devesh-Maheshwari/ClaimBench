"""Audit orchestration errors (generic)."""


class AuditRecipeError(ValueError):
    """Raised when an audit request cannot be mapped to a supported recipe."""
