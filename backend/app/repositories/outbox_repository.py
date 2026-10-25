"""Repository for Transactional Outbox pattern message persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import OutboxMessage


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Publication attempts after which a message is no longer re-dispatched.
# Transient broker failures are retried by the recovery sweep until this cap;
# permanently undeliverable messages (for example a malformed payload) would
# otherwise be retried forever.
MAX_DELIVERY_ATTEMPTS = 10


class OutboxRepository:
    """Operations for persisting and querying outbox messages."""

    @staticmethod
    def create_message(
        db: Session,
        topic: str,
        payload: dict[str, Any],
    ) -> OutboxMessage:
        """Create an outbox message within the current database transaction."""
        msg_id = str(uuid.uuid4())
        msg = OutboxMessage(
            id=msg_id,
            topic=topic,
            payload=json.dumps(payload),
            status="pending",
            created_at=_utc_now(),
            retry_count=0,
        )
        db.add(msg)
        db.flush()
        return msg

    @staticmethod
    def get_pending_messages(
        db: Session,
        limit: int = 50,
        max_attempts: int = MAX_DELIVERY_ATTEMPTS,
    ) -> list[OutboxMessage]:
        """Fetch undelivered outbox messages: ``pending``, or ``failed`` under the retry cap.

        ``dispatch_outbox_message`` records broker failures as ``failed`` with
        the error precisely so the recovery sweep can re-dispatch them.
        Selecting only ``pending`` here would strand every message that ever
        hit a transient broker failure — the recovery path would be dead code.
        """
        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.status.in_(("pending", "failed")),
                OutboxMessage.retry_count < max_attempts,
            )
            .order_by(OutboxMessage.created_at.asc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def mark_published(db: Session, message_id: str) -> None:
        """Mark an outbox message as successfully published to the message broker."""
        msg = db.get(OutboxMessage, message_id)
        if msg is not None:
            msg.status = "published"
            msg.published_at = _utc_now()
            db.flush()

    @staticmethod
    def mark_failed(db: Session, message_id: str, error: str) -> None:
        """Record a publication failure and increment retry count."""
        msg = db.get(OutboxMessage, message_id)
        if msg is not None:
            msg.status = "failed"
            msg.retry_count += 1
            msg.last_error = error[:1000]
            db.flush()
