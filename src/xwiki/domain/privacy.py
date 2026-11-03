"""Fail-closed privacy policy for NEW product flows (not legacy publishing).

This policy can deny unsupported transfers; it is not an authentication system,
a provider sandbox or an implemented public sharing workflow.
"""

from dataclasses import dataclass

from .enums import DataDestination, PrivacyScope
from .errors import ContractError, PermissionDenied
from .validation import enum_value


@dataclass(frozen=True, slots=True)
class ProcessingConsent:
    destination: DataDestination
    granted: bool = False

    def __post_init__(self) -> None:
        enum_value(self.destination, DataDestination, "destination")
        if type(self.granted) is not bool:
            raise ContractError("consent.granted must be a boolean")


def can_transfer(
    source_scope: PrivacyScope,
    destination: DataDestination,
    *,
    consent: ProcessingConsent | None = None,
) -> bool:
    enum_value(source_scope, PrivacyScope, "source_scope")
    enum_value(destination, DataDestination, "destination")
    if destination is DataDestination.DEVICE:
        return True
    if destination is DataDestination.PUBLIC_WEB:
        return False  # A separate, audited publish authorization is required.
    return bool(
        source_scope is PrivacyScope.PRIVATE
        and consent is not None
        and consent.destination is DataDestination.EXTERNAL_MODEL
        and consent.granted
    )


def require_transfer(
    source_scope: PrivacyScope,
    destination: DataDestination,
    *,
    consent: ProcessingConsent | None = None,
) -> None:
    if not can_transfer(source_scope, destination, consent=consent):
        raise PermissionDenied(f"transfer to {destination.value} is not authorized")
