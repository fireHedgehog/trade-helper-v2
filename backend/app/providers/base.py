"""Provider registry: the code-side authority on what credentials each
provider needs and how to verify them.

Adding a provider here (plus a seed row in a schema migration) is all it
takes to surface it on the Credentials page.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

# (status, short_detail) — status is one of "healthy" | "invalid".
VerifyResult = tuple[str, str]
Verifier = Callable[[Mapping[str, str], "ProviderSpec"], Awaitable[VerifyResult]]


@dataclass(frozen=True)
class FieldSpec:
    name: str          # machine name, also the keychain sub-key
    label: str         # UI label
    env_var: str       # environment-variable fallback for this field
    placeholder: str = ""


# Not frozen: tests swap ``verifier`` for a stub, and it is a harmless seam.
@dataclass
class ProviderSpec:
    key: str
    label: str
    description: str
    credential_name: str
    fields: list[FieldSpec]
    verifier: Verifier = field(repr=False)

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def get_field(self, name: str) -> FieldSpec:
        for f in self.fields:
            if f.name == name:
                return f
        raise KeyError(name)


_REGISTRY: dict[str, ProviderSpec] = {}


def register(spec: ProviderSpec) -> None:
    _REGISTRY[spec.key] = spec


def get_provider(key: str) -> ProviderSpec | None:
    return _REGISTRY.get(key)


def all_providers() -> list[ProviderSpec]:
    return list(_REGISTRY.values())
