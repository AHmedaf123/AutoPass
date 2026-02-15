"""
Custom Exception Hierarchy
Domain and application-level exceptions
"""


class DomainException(Exception):
    """Base exception for all domain errors"""
    pass


class AuthenticationException(DomainException):
    """Authentication failed"""
    pass


class AuthorizationException(DomainException):
    """User not authorized for this operation"""
    pass


class ValidationException(DomainException):
    """Data validation failed"""
    
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class RepositoryException(DomainException):
    """Database operation failed"""
    pass


class ResourceNotFoundException(DomainException):
    """Requested resource not found"""
    
    def __init__(self, resource_type: str, identifier: str):
        self.resource_type = resource_type
        self.identifier = identifier
        super().__init__(f"{resource_type} not found: {identifier}")


class DuplicateResourceException(DomainException):
    """Resource already exists"""
    
    def __init__(self, resource_type: str, field: str, value: str):
        self.resource_type = resource_type
        self.field = field
        self.value = value
        super().__init__(f"{resource_type} with {field}='{value}' already exists")


class RateLimitException(DomainException):
    """Rate limit exceeded"""
    
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after} seconds")
