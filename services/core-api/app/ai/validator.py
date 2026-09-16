from .exceptions import ExtractionValidationError


def validate_fields(fields, registry):
    valid = []

    for field in fields:
        item = registry.get(field.field_key)
        if item is None:
            continue

        if not 0 <= field.confidence <= 1:
            raise ExtractionValidationError("invalid confidence")

        if getattr(item, "value_type", None) != field.value_type:
            continue

        valid.append(field)

    return valid
