import json

from .exceptions import InvalidAIResponse
from .schemas import ExtractionResult
from .validator import validate_fields


class ProfileExtractor:
    def __init__(self, provider, registry):
        self.provider = provider
        self.registry = registry

    def extract(self, resume_text: str):
        response = self.provider.complete(resume_text)

        try:
            payload = json.loads(response)
        except Exception as exc:
            raise InvalidAIResponse("invalid json") from exc

        result = ExtractionResult.model_validate(payload)
        return validate_fields(result.fields, self.registry)
