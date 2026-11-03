"""Explicit failures rather than silently coercing invalid model output."""


class ContractError(ValueError):
    """The supplied entity or wire data violates a domain invariant."""


class EvidenceError(ContractError):
    """An evidence reference is unresolvable, inconsistent, or outside its source."""


class TransitionError(ContractError):
    """A requested proposal status change is not legal."""


class PermissionDenied(ContractError):
    """A data transfer is not authorized by the domain-level privacy policy."""
