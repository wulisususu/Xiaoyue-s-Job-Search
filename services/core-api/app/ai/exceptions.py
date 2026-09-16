class ExtractionError(Exception):
    """Base extraction failure."""


class InvalidAIResponse(ExtractionError):
    pass


class ExtractionValidationError(ExtractionError):
    pass
