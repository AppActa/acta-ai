class NotFoundError(LookupError):
    """Recurso ausente no escopo autenticado."""

class AuthorizationError(PermissionError):
    """Acesso negado ao recurso solicitado."""
