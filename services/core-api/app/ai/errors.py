"""Domain error taxonomy shared by every extraction provider.

The business layer catches these (or their common base) instead of
transport-specific exceptions, so swapping endpoints never changes
error handling at call sites.
"""
from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for every AI provider failure in the unified contract."""


class ProviderInputError(ProviderError):
    """The resume input violates a provider boundary before any network call."""


class ProviderRequestError(ProviderError):
    """The provider request could not be delivered or was rejected (HTTP >= 400)."""


class ProviderTimeoutError(ProviderError):
    """The provider did not answer within the configured timeout."""


class ProviderResponseError(ProviderError):
    """The provider answered, but the response is unusable as an extraction bundle."""
