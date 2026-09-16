from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    field_key: str
    value: str
    value_type: str = "string"
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    fields: list[ExtractedField]
