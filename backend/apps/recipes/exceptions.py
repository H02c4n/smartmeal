class RecipeLockedError(ValueError):
    """A non-draft recipe version (or one of its lines) was modified."""
