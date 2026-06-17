from fastapi import HTTPException, status

class BaseCustomException(Exception):
    """Base exception for custom application errors."""
    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class AuthenticationError(BaseCustomException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED)

class AuthorizationError(BaseCustomException):
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, status.HTTP_403_FORBIDDEN)

class NotFoundError(BaseCustomException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status.HTTP_404_NOT_FOUND)

class ValidationError(BaseCustomException):
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status.HTTP_422_UNPROCESSABLE_ENTITY)

class ResumeProcessingError(BaseCustomException):
    def __init__(self, message: str = "Resume processing failed"):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)

class AIServiceError(BaseCustomException):
    def __init__(self, message: str = "AI service error"):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR)
