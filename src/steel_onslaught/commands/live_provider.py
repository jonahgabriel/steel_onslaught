"""Secret-free, process-local authority for one live-provider completion.

The grant binds an already authenticated match launch to one exact model and
provider identity.  It carries no endpoint, secret reference, credential, or
provider response content.  Consumption is process-local and deliberately
non-durable; restart recovery remains outside this capability.
"""

from __future__ import annotations

from threading import Lock
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from steel_onslaught.commands.authority import PrincipalId, SessionId
from steel_onslaught.contracts.player_selection import (
    ModelIdentityId,
    ProviderBindingId,
    Sha256Digest,
)


class LiveProviderCapabilityError(ValueError):
    """Base error for the process-local one-shot capability."""


class LiveProviderGrantBindingError(LiveProviderCapabilityError):
    """The authorization request does not exactly match the frozen grant."""


class LiveProviderGrantConsumedError(LiveProviderCapabilityError):
    """The bounded live-provider authorization has already been consumed."""


class ModelSOLiveProviderLaunchGrant(BaseModel):
    """Closed, secret-free authority for one exact live-provider launch."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal["1"] = "1"
    kind: Literal["steel_onslaught.live_provider_launch_grant"] = (
        "steel_onslaught.live_provider_launch_grant"
    )
    creator_principal_id: PrincipalId
    creator_session_id: SessionId
    launch_command_id: UUID
    launch_command_sha256: Sha256Digest
    overlay_sha256: Sha256Digest
    roster_sha256: Sha256Digest
    model_identity_id: ModelIdentityId
    provider_id: ProviderBindingId
    # A launch grant authorizes a bounded match budget, not a single turn.
    # Keep the legacy default at one for callers that explicitly want a
    # one-shot grant; live browser launches set this to a multi-turn budget.
    max_completions: int = Field(default=1, gt=0, le=256)


class ProcessLocalOneShotLiveProviderCapability:
    """Atomically authorize the exact frozen grant at most once."""

    def __init__(self, *, grant: ModelSOLiveProviderLaunchGrant) -> None:
        self._grant = grant
        self._consumption_count = 0
        self._lock = Lock()

    @property
    def consumption_count(self) -> int:
        with self._lock:
            return self._consumption_count

    def consume(
        self,
        *,
        creator_principal_id: PrincipalId,
        creator_session_id: SessionId,
        launch_command_id: UUID,
        launch_command_sha256: Sha256Digest,
        overlay_sha256: Sha256Digest,
        roster_sha256: Sha256Digest,
        model_identity_id: ModelIdentityId,
        provider_id: ProviderBindingId,
    ) -> ModelSOLiveProviderLaunchGrant:
        """Consume the grant only when every secret-free binding is exact."""

        candidate = {
            "creator_principal_id": creator_principal_id,
            "creator_session_id": creator_session_id,
            "launch_command_id": launch_command_id,
            "launch_command_sha256": launch_command_sha256,
            "overlay_sha256": overlay_sha256,
            "roster_sha256": roster_sha256,
            "model_identity_id": model_identity_id,
            "provider_id": provider_id,
        }
        with self._lock:
            if self._consumption_count >= self._grant.max_completions:
                raise LiveProviderGrantConsumedError("live provider grant is already consumed")
            for field, value in candidate.items():
                if getattr(self._grant, field) != value:
                    raise LiveProviderGrantBindingError(
                        f"live provider grant binding mismatch: {field}"
                    )
            self._consumption_count += 1
            return self._grant


__all__ = [
    "LiveProviderCapabilityError",
    "LiveProviderGrantBindingError",
    "LiveProviderGrantConsumedError",
    "ModelSOLiveProviderLaunchGrant",
    "ProcessLocalOneShotLiveProviderCapability",
]
