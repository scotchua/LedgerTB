"""AI provider choice determines which third party receives client transaction
descriptions and account data. Changing AI_PROVIDER is a real data-handling
decision, not merely a configuration toggle.
"""

from dataclasses import dataclass
from typing import Dict
from urllib.parse import urlparse

from .anthropic_format import AnthropicRequest
from .openai_format import OpenAIRequest


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    wire_format: str
    base_url: str
    model: str


PROVIDERS: Dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        name="anthropic",
        wire_format="anthropic",
        base_url="https://api.anthropic.com",
        model="claude-sonnet-5",
    ),
    "openai": ProviderSpec(
        name="openai",
        wire_format="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-5-mini",
    ),
}


class ProviderConfigurationError(ValueError):
    pass


def get_provider(name: str) -> ProviderSpec:
    normalized = (name or "").strip().lower()
    try:
        return PROVIDERS[normalized]
    except KeyError:
        raise ProviderConfigurationError(
            f"Unknown AI_PROVIDER {name!r}; expected one of: anthropic, openai."
        ) from None


def validate_provider_url(spec: ProviderSpec, actual_url: str) -> None:
    registered = get_provider(spec.name)
    if spec.base_url != registered.base_url:
        raise ProviderConfigurationError(
            f"Refusing altered base URL for {spec.name!r}."
        )
    expected = urlparse(registered.base_url)
    actual = urlparse(actual_url)
    if (
        actual.scheme != expected.scheme
        or actual.hostname != expected.hostname
        or actual.port != expected.port
    ):
        raise ProviderConfigurationError(
            f"Refusing {spec.name} request to unexpected host "
            f"{actual.hostname or actual_url!r}; expected {expected.hostname!r}."
        )


def create_request(spec: ProviderSpec, api_key: str, tool, prompt: str):
    if not api_key:
        raise ProviderConfigurationError(
            f"No API key is configured for selected AI provider {spec.name!r}."
        )
    if spec.wire_format == "anthropic":
        return AnthropicRequest(spec, api_key, tool, prompt)
    if spec.wire_format == "openai":
        return OpenAIRequest(spec, api_key, tool, prompt)
    raise ProviderConfigurationError(
        f"Unsupported wire format {spec.wire_format!r} for {spec.name!r}."
    )
