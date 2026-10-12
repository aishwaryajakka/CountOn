"""Owner-only preferences; email targets come from confirmed Supabase identity."""

from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, InvalidExpectationError
from app.db.models import NotificationDelivery, NotificationPreference
from app.integrations.provider import ProviderError
from app.notifications.delivery import encrypt


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/notification-preferences",
    tags=["notifications"],
    dependencies=[Depends(no_store)],
)
Database = Annotated[Session, Depends(get_db)]


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    email_enabled: bool = False
    mismatch_enabled: bool = True
    deadline_enabled: bool = False
    connection_enabled: bool = True
    quiet_enabled: bool = False
    quiet_start_hour: int = Field(default=22, ge=0, le=23)
    quiet_end_hour: int = Field(default=8, ge=0, le=23)
    timezone: str = Field(default="UTC", max_length=64)

    @model_validator(mode="after")
    def validate_zone(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Select a valid IANA timezone") from None
        if self.quiet_enabled and self.quiet_start_hour == self.quiet_end_hour:
            raise ValueError("Quiet hours must leave a delivery window")
        return self


def confirmed_email(settings, authorization, user_id):
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise AuthenticationError()
    try:
        with (
            httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client,
            client.stream(
                "GET",
                settings.supabase_url.rstrip("/") + "/auth/v1/user",
                headers={
                    "Authorization": authorization,
                    "apikey": settings.supabase_publishable_key,
                },
            ) as response,
        ):
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise AuthenticationError()
            import json

            if response.status_code in (401, 403):
                raise AuthenticationError()
            if response.status_code != 200:
                raise ProviderError("PROVIDER_UNAVAILABLE")
            identity = json.loads(raw)
        email = identity.get("email")
        if identity.get("id") != str(user_id):
            raise AuthenticationError()
        if (
            not identity.get("email_confirmed_at")
            or not isinstance(email, str)
            or len(email) > 254
            or "\n" in email
            or "\r" in email
            or "@" not in email
        ):
            raise InvalidExpectationError(
                "Confirm your account email before enabling email notifications"
            )
        return email
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise ProviderError("PROVIDER_UNAVAILABLE") from None


@router.get("", response_model=Preferences)
def get(db: Database, user: CurrentUser):
    return db.get(NotificationPreference, user.id) or Preferences()


@router.put("", response_model=Preferences)
def put(payload: Preferences, request: Request, db: Database, user: CurrentUser):
    settings = get_settings()
    if payload.email_enabled and not settings.notification_email_enabled:
        raise InvalidExpectationError(
            "Email notifications are not configured on this deployment"
        )
    # Network verification outside the row lock; never accept a browser recipient/user_id.
    recipient = (
        confirmed_email(settings, request.headers.get("Authorization", ""), user.id)
        if payload.email_enabled
        else None
    )
    db.execute(
        insert(NotificationPreference)
        .values(user_id=user.id)
        .on_conflict_do_nothing(index_elements=["user_id"])
    )
    pref = db.scalar(
        select(NotificationPreference)
        .where(NotificationPreference.user_id == user.id)
        .with_for_update()
    )
    if pref is None:
        pref = NotificationPreference(user_id=user.id)
        db.add(pref)
    for field, value in payload.model_dump().items():
        setattr(pref, field, value)
    pref.encrypted_recipient = (
        encrypt(settings, {"email": recipient}, user.id) if recipient else None
    )
    if not payload.email_enabled:
        for delivery in db.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.user_id == user.id,
                NotificationDelivery.status == "pending",
            )
            .with_for_update()
        ):
            delivery.status = "cancelled"
    db.commit()
    return pref


@router.get("/delivery-history")
def history(db: Database, user: CurrentUser):
    return [
        {
            "id": item.id,
            "notification_id": item.notification_id,
            "channel": item.channel,
            "status": item.status,
            "attempt_count": item.attempt_count,
            "last_error": item.last_error,
            "sent_at": item.sent_at,
        }
        for item in db.scalars(
            select(NotificationDelivery)
            .where(NotificationDelivery.user_id == user.id)
            .order_by(NotificationDelivery.next_run_at.desc())
            .limit(100)
        )
    ]
