"""Route by task, not by defaulting everything to the priciest model.

Per docs/AGENT_CONTRACTS.md #78: a contract specifies a capability tier, not an
exact model. The router is the one place that maps tiers to provider/model.
"""

from enum import StrEnum

from pydantic import BaseModel


class ModelTier(StrEnum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    HIGH_REASONING = "HIGH_REASONING"
    HIGH_PRECISION_EXTRACTION = "HIGH_PRECISION_EXTRACTION"


class RoutedModel(BaseModel):
    provider: str
    model: str


class ModelRouter:
    def __init__(self, routes: dict[ModelTier, RoutedModel]) -> None:
        self._routes = routes

    def resolve(self, tier: ModelTier) -> RoutedModel:
        try:
            return self._routes[tier]
        except KeyError:
            raise ValueError(f"No route configured for model tier {tier}") from None


DEFAULT_OPENAI_ROUTES: dict[ModelTier, RoutedModel] = {
    ModelTier.FAST: RoutedModel(provider="openai", model="gpt-4o-mini"),
    ModelTier.STANDARD: RoutedModel(provider="openai", model="gpt-4o"),
    ModelTier.HIGH_REASONING: RoutedModel(provider="openai", model="o3"),
    ModelTier.HIGH_PRECISION_EXTRACTION: RoutedModel(provider="openai", model="gpt-4o"),
}
