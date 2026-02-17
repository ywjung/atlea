"""Webhook delivery service

Handles webhook creation, management, and delivery with retry logic and HMAC signing.
PostgreSQL-backed storage via Webhook ORM model.
"""

import asyncio
import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import httpx
from loguru import logger

from .models import (
    Webhook as WebhookPydantic,
    WebhookCreate,
    WebhookUpdate,
    WebhookEvent,
    WebhookDelivery
)


def _orm_to_pydantic(orm_wh) -> WebhookPydantic:
    """Convert ORM Webhook to Pydantic Webhook model."""
    events_raw = orm_wh.events or []
    events = []
    for e in events_raw:
        try:
            events.append(WebhookEvent(e))
        except ValueError:
            continue

    return WebhookPydantic(
        webhook_id=str(orm_wh.id),
        name=orm_wh.name,
        url=orm_wh.url,
        events=events,
        secret=orm_wh.secret,
        is_active=orm_wh.is_active,
        created_at=orm_wh.created_at,
        updated_at=orm_wh.updated_at,
        created_by=str(orm_wh.user_id),
        retry_count=3,
        timeout_seconds=30,
    )


class WebhookService:
    """웹훅 관리 및 전송 서비스 (PostgreSQL 기반)"""

    def __init__(self):
        """초기화

        Args:
        """
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_connections=100)
        )

    async def create_webhook(
        self,
        webhook_data: WebhookCreate,
        user_id: str
    ) -> WebhookPydantic:
        """웹훅 생성"""
        from ..database.connection import AsyncSessionFactory
        from ..database.models.webhook import Webhook as WebhookORM

        webhook_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        async with AsyncSessionFactory() as session:
            orm_wh = WebhookORM(
                id=webhook_id,
                user_id=uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
                name=webhook_data.name,
                url=webhook_data.url,
                events=[e.value for e in webhook_data.events],
                secret=webhook_data.secret,
                is_active=webhook_data.is_active,
                headers={},
            )
            session.add(orm_wh)
            await session.commit()
            await session.refresh(orm_wh)

        result = _orm_to_pydantic(orm_wh)
        logger.info(f"Webhook created: {webhook_id} by user {user_id}")
        return result

    async def get_webhook(self, webhook_id: str) -> Optional[WebhookPydantic]:
        """웹훅 조회"""
        from ..database.connection import AsyncSessionFactory
        from ..database.models.webhook import Webhook as WebhookORM
        from sqlalchemy import select

        try:
            wh_uuid = uuid.UUID(webhook_id)
        except ValueError:
            return None

        async with AsyncSessionFactory() as session:
            stmt = select(WebhookORM).where(WebhookORM.id == wh_uuid)
            result = await session.execute(stmt)
            orm_wh = result.scalar_one_or_none()

            if not orm_wh:
                return None

            return _orm_to_pydantic(orm_wh)

    async def list_webhooks(self, user_id: str) -> List[WebhookPydantic]:
        """사용자의 웹훅 목록 조회"""
        from ..database.connection import AsyncSessionFactory
        from ..database.models.webhook import Webhook as WebhookORM
        from sqlalchemy import select

        try:
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            return []

        async with AsyncSessionFactory() as session:
            stmt = (
                select(WebhookORM)
                .where(WebhookORM.user_id == user_uuid)
                .order_by(WebhookORM.created_at.desc())
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

            return [_orm_to_pydantic(r) for r in rows]

    async def update_webhook(
        self,
        webhook_id: str,
        webhook_data: WebhookUpdate,
        user_id: str
    ) -> Optional[WebhookPydantic]:
        """웹훅 업데이트"""
        from ..database.connection import AsyncSessionFactory
        from ..database.models.webhook import Webhook as WebhookORM
        from sqlalchemy import select

        try:
            wh_uuid = uuid.UUID(webhook_id)
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            return None

        async with AsyncSessionFactory() as session:
            stmt = select(WebhookORM).where(
                WebhookORM.id == wh_uuid,
                WebhookORM.user_id == user_uuid,
            )
            result = await session.execute(stmt)
            orm_wh = result.scalar_one_or_none()

            if not orm_wh:
                return None

            if webhook_data.name is not None:
                orm_wh.name = webhook_data.name
            if webhook_data.url is not None:
                orm_wh.url = webhook_data.url
            if webhook_data.events is not None:
                orm_wh.events = [e.value for e in webhook_data.events]
            if webhook_data.secret is not None:
                orm_wh.secret = webhook_data.secret
            if webhook_data.is_active is not None:
                orm_wh.is_active = webhook_data.is_active

            await session.commit()
            await session.refresh(orm_wh)

            logger.info(f"Webhook updated: {webhook_id} by user {user_id}")
            return _orm_to_pydantic(orm_wh)

    async def delete_webhook(self, webhook_id: str, user_id: str) -> bool:
        """웹훅 삭제"""
        from ..database.connection import AsyncSessionFactory
        from ..database.models.webhook import Webhook as WebhookORM
        from sqlalchemy import select

        try:
            wh_uuid = uuid.UUID(webhook_id)
            user_uuid = uuid.UUID(user_id)
        except ValueError:
            return False

        async with AsyncSessionFactory() as session:
            stmt = select(WebhookORM).where(
                WebhookORM.id == wh_uuid,
                WebhookORM.user_id == user_uuid,
            )
            result = await session.execute(stmt)
            orm_wh = result.scalar_one_or_none()

            if not orm_wh:
                return False

            await session.delete(orm_wh)
            await session.commit()

        logger.info(f"Webhook deleted: {webhook_id} by user {user_id}")
        return True

    def _generate_signature(self, secret: str, payload: str) -> str:
        """HMAC-SHA256 서명 생성"""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    async def _deliver_webhook(
        self,
        webhook: WebhookPydantic,
        event_type: WebhookEvent,
        payload: Dict[str, Any],
        retry_attempt: int = 0
    ) -> WebhookDelivery:
        """웹훅 전송 (내부 메서드)"""
        delivery_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        delivery = WebhookDelivery(
            delivery_id=delivery_id,
            webhook_id=webhook.webhook_id,
            event_type=event_type,
            payload=payload,
            status="pending",
            created_at=now,
            retry_count=retry_attempt
        )

        try:
            payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(',', ':'))

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "ChatbotWebhook/1.0",
                "X-Webhook-Event": event_type.value,
                "X-Webhook-Delivery": delivery_id,
                "X-Webhook-Timestamp": now.isoformat()
            }

            if webhook.secret:
                signature = self._generate_signature(webhook.secret, payload_json)
                headers["X-Webhook-Signature"] = f"sha256={signature}"

            response = await self.http_client.post(
                webhook.url,
                content=payload_json,
                headers=headers,
                timeout=webhook.timeout_seconds
            )

            delivery.status = "success" if response.status_code < 400 else "failed"
            delivery.response_status = response.status_code
            delivery.response_body = response.text[:500]
            delivery.delivered_at = datetime.now(timezone.utc)

            if delivery.status == "success":
                logger.info(
                    f"Webhook delivered: {delivery_id} to {webhook.url} "
                    f"(status: {response.status_code})"
                )
            else:
                delivery.error_message = f"HTTP {response.status_code}"
                logger.warning(
                    f"Webhook delivery failed: {delivery_id} to {webhook.url} "
                    f"(status: {response.status_code})"
                )

        except httpx.TimeoutException:
            delivery.status = "failed"
            delivery.error_message = "Request timeout"
            delivery.delivered_at = datetime.now(timezone.utc)
            logger.error(f"Webhook delivery timeout: {delivery_id} to {webhook.url}")

        except Exception as e:
            delivery.status = "failed"
            delivery.error_message = str(e)[:200]
            delivery.delivered_at = datetime.now(timezone.utc)
            logger.error(f"Webhook delivery error: {delivery_id} to {webhook.url} - {e}")

        return delivery

    async def trigger_event(
        self,
        event_type: WebhookEvent,
        payload: Dict[str, Any]
    ) -> List[WebhookDelivery]:
        """이벤트 트리거 - 모든 해당 웹훅에 전송"""
        from ..database.connection import AsyncSessionFactory
        from ..database.models.webhook import Webhook as WebhookORM
        from sqlalchemy import select

        async with AsyncSessionFactory() as session:
            stmt = select(WebhookORM).where(WebhookORM.is_active == True)
            result = await session.execute(stmt)
            rows = result.scalars().all()

        deliveries = []
        for orm_wh in rows:
            try:
                webhook = _orm_to_pydantic(orm_wh)

                if event_type.value not in [e.value for e in webhook.events]:
                    continue

                delivery = await self._deliver_with_retry(webhook, event_type, payload)
                deliveries.append(delivery)
            except Exception as e:
                logger.error(f"Failed to process webhook {orm_wh.id}: {e}")
                continue

        return deliveries

    async def _deliver_with_retry(
        self,
        webhook: WebhookPydantic,
        event_type: WebhookEvent,
        payload: Dict[str, Any]
    ) -> WebhookDelivery:
        """재시도 로직을 포함한 웹훅 전송"""
        delivery = None

        for attempt in range(webhook.retry_count + 1):
            delivery = await self._deliver_webhook(webhook, event_type, payload, attempt)

            if delivery.status == "success":
                break

            if attempt < webhook.retry_count:
                wait_time = min(2 ** attempt, 60)
                logger.info(
                    f"Webhook delivery retry {attempt + 1}/{webhook.retry_count} "
                    f"for {webhook.webhook_id} in {wait_time}s"
                )
                await asyncio.sleep(wait_time)

        return delivery

    async def test_webhook(
        self,
        webhook_id: str,
        event_type: WebhookEvent,
        user_id: str
    ) -> WebhookDelivery:
        """웹훅 테스트"""
        webhook = await self.get_webhook(webhook_id)
        if not webhook:
            raise ValueError("웹훅을 찾을 수 없습니다")

        if webhook.created_by != user_id:
            raise ValueError("웹훅에 대한 권한이 없습니다")

        test_payload = {
            "event_type": event_type.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test": True,
            "data": {
                "message": "This is a test webhook delivery",
                "webhook_id": webhook_id
            }
        }

        delivery = await self._deliver_webhook(webhook, event_type, test_payload)
        return delivery

    async def get_delivery_logs(
        self,
        webhook_id: str,
        user_id: str,
        limit: int = 50
    ) -> List[WebhookDelivery]:
        """웹훅 전송 기록 조회

        Note: Delivery logs are no longer persisted after PG migration.
        Returns empty list. Use application logs for delivery history.
        """
        return []

    async def cleanup(self):
        """리소스 정리"""
        await self.http_client.aclose()
