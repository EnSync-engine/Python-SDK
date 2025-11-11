"""
Error handling for EnSync Python SDK.
"""

# Generic error message for general errors
GENERIC_MESSAGE = "An error occurred with the EnSync service."


class EnSyncError(Exception):
    """
    Base exception class for EnSync SDK errors.
    
    Attributes:
        message (str): Error message
        error_type (str): Type of error
        cause (Exception, optional): Original exception that caused this error
    """
    
    def __init__(self, message=GENERIC_MESSAGE, error_type="EnSyncError", cause=None):
        """
        Initialize EnSync error.
        
        Args:
            message: Error message
            error_type: Type of error
            cause: Original exception that caused this error
        """
        self.message = message
        self.error_type = error_type
        self.cause = cause
        super().__init__(self.message)
    
    def __str__(self):
        """Return string representation of the error."""
        if self.cause:
            return f"{self.error_type}: {self.message} (Caused by: {str(self.cause)})"
        return f"{self.error_type}: {self.message}"
