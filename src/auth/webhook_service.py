"""Webhook delivery service

Handles webhook creation, management, and delivery with retry logic and HMAC signing.
"""

import asyncio
import hmac
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import httpx
from loguru import logger
from redis import Redis

from .models import (
    Webhook,
    WebhookCreate,
    WebhookUpdate,
    WebhookEvent,
    WebhookDelivery
)


class WebhookService:
    """웹훅 관리 및 전송 서비스"""

    def __init__(self, redis: Redis):
        self.redis = redis
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_connections=100)
        )

    async def create_webhook(
        self,
        webhook_data: WebhookCreate,
        user_id: str
    ) -> Webhook:
        """웹훅 생성

        Args:
            webhook_data: 웹훅 생성 데이터
            user_id: 생성자 사용자 ID

        Returns:
            생성된 웹훅 객체
        """
        webhook_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        webhook = Webhook(
            webhook_id=webhook_id,
            name=webhook_data.name,
            url=webhook_data.url,
            events=[e.value for e in webhook_data.events],
            secret=webhook_data.secret,
            is_active=webhook_data.is_active,
            created_at=now,
            updated_at=now,
            created_by=user_id,
            retry_count=webhook_data.retry_count,
            timeout_seconds=webhook_data.timeout_seconds
        )

        # Redis에 저장
        self.redis.hset(
            f"webhook:{webhook_id}",
            mapping={
                "webhook_id": webhook_id,
                "name": webhook.name,
                "url": webhook.url,
                "events": json.dumps(webhook.events),
                "secret": webhook.secret or "",
                "is_active": str(webhook.is_active),
                "created_at": webhook.created_at.isoformat(),
                "updated_at": webhook.updated_at.isoformat(),
                "created_by": user_id,
                "total_deliveries": str(webhook.total_deliveries),
                "successful_deliveries": str(webhook.successful_deliveries),
                "failed_deliveries": str(webhook.failed_deliveries),
                "retry_count": str(webhook.retry_count),
                "timeout_seconds": str(webhook.timeout_seconds)
            }
        )

        # 사용자별 웹훅 인덱스
        self.redis.sadd(f"user:{user_id}:webhooks", webhook_id)

        logger.info(f"Webhook created: {webhook_id} by user {user_id}")
        return webhook

    async def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        """웹훅 조회

        Args:
            webhook_id: 웹훅 ID

        Returns:
            웹훅 객체 또는 None
        """
        data = self.redis.hgetall(f"webhook:{webhook_id}")
        if not data:
            return None

        def get_field(field_name: str, default=None):
            """Helper to get field from data"""
            raw = data.get(field_name.encode()) or data.get(field_name)
            if raw is None:
                return default
            return raw.decode() if isinstance(raw, bytes) else raw

        return Webhook(
            webhook_id=get_field("webhook_id"),
            name=get_field("name"),
            url=get_field("url"),
            events=json.loads(get_field("events", "[]")),
            secret=get_field("secret") or None,
            is_active=get_field("is_active") == "True",
            created_at=datetime.fromisoformat(get_field("created_at")),
            updated_at=datetime.fromisoformat(get_field("updated_at")),
            created_by=get_field("created_by"),
            total_deliveries=int(get_field("total_deliveries", 0)),
            successful_deliveries=int(get_field("successful_deliveries", 0)),
            failed_deliveries=int(get_field("failed_deliveries", 0)),
            last_delivery_at=datetime.fromisoformat(get_field("last_delivery_at")) if get_field("last_delivery_at") else None,
            last_success_at=datetime.fromisoformat(get_field("last_success_at")) if get_field("last_success_at") else None,
            last_failure_at=datetime.fromisoformat(get_field("last_failure_at")) if get_field("last_failure_at") else None,
            retry_count=int(get_field("retry_count", 3)),
            timeout_seconds=int(get_field("timeout_seconds", 30))
        )

    async def list_webhooks(self, user_id: str) -> List[Webhook]:
        """사용자의 웹훅 목록 조회

        Args:
            user_id: 사용자 ID

        Returns:
            웹훅 목록
        """
        webhook_ids = self.redis.smembers(f"user:{user_id}:webhooks")
        if not webhook_ids:
            return []

        # Pipeline을 사용하여 모든 웹훅 데이터를 일괄 조회 (N+1 → 1 쿼리)
        webhook_id_strs = [wid.decode() if isinstance(wid, bytes) else wid for wid in webhook_ids]
        pipe = self.redis.pipeline()
        for webhook_id in webhook_id_strs:
            pipe.hgetall(f"webhook:{webhook_id}")
        webhook_data_list = pipe.execute()

        webhooks = []
        for data in webhook_data_list:
            if not data:
                continue

            def get_field(field_name: str, default=None):
                """Helper to get field from data"""
                raw = data.get(field_name.encode()) or data.get(field_name)
                if raw is None:
                    return default
                return raw.decode() if isinstance(raw, bytes) else raw

            try:
                webhook = Webhook(
                    webhook_id=get_field("webhook_id"),
                    name=get_field("name"),
                    url=get_field("url"),
                    events=json.loads(get_field("events", "[]")),
                    secret=get_field("secret") or None,
                    is_active=get_field("is_active") == "True",
                    created_at=datetime.fromisoformat(get_field("created_at")),
                    updated_at=datetime.fromisoformat(get_field("updated_at")),
                    created_by=get_field("created_by"),
                    total_deliveries=int(get_field("total_deliveries", 0)),
                    successful_deliveries=int(get_field("successful_deliveries", 0)),
                    failed_deliveries=int(get_field("failed_deliveries", 0)),
                    last_delivery_at=datetime.fromisoformat(get_field("last_delivery_at")) if get_field("last_delivery_at") else None,
                    last_success_at=datetime.fromisoformat(get_field("last_success_at")) if get_field("last_success_at") else None,
                    last_failure_at=datetime.fromisoformat(get_field("last_failure_at")) if get_field("last_failure_at") else None,
                    retry_count=int(get_field("retry_count", 3)),
                    timeout_seconds=int(get_field("timeout_seconds", 30))
                )
                webhooks.append(webhook)
            except Exception:
                continue

        return sorted(webhooks, key=lambda w: w.created_at, reverse=True)

    async def update_webhook(
        self,
        webhook_id: str,
        webhook_data: WebhookUpdate,
        user_id: str
    ) -> Optional[Webhook]:
        """웹훅 업데이트

        Args:
            webhook_id: 웹훅 ID
            webhook_data: 업데이트 데이터
            user_id: 요청 사용자 ID

        Returns:
            업데이트된 웹훅 객체 또는 None
        """
        webhook = await self.get_webhook(webhook_id)
        if not webhook or webhook.created_by != user_id:
            return None

        update_data = {}
        if webhook_data.name is not None:
            update_data["name"] = webhook_data.name
        if webhook_data.url is not None:
            update_data["url"] = webhook_data.url
        if webhook_data.events is not None:
            update_data["events"] = json.dumps([e.value for e in webhook_data.events])
        if webhook_data.secret is not None:
            update_data["secret"] = webhook_data.secret
        if webhook_data.is_active is not None:
            update_data["is_active"] = str(webhook_data.is_active)
        if webhook_data.retry_count is not None:
            update_data["retry_count"] = str(webhook_data.retry_count)
        if webhook_data.timeout_seconds is not None:
            update_data["timeout_seconds"] = str(webhook_data.timeout_seconds)

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        if update_data:
            self.redis.hset(f"webhook:{webhook_id}", mapping=update_data)

        logger.info(f"Webhook updated: {webhook_id} by user {user_id}")
        return await self.get_webhook(webhook_id)

    async def delete_webhook(self, webhook_id: str, user_id: str) -> bool:
        """웹훅 삭제

        Args:
            webhook_id: 웹훅 ID
            user_id: 요청 사용자 ID

        Returns:
            삭제 성공 여부
        """
        webhook = await self.get_webhook(webhook_id)
        if not webhook or webhook.created_by != user_id:
            return False

        # 웹훅 삭제
        self.redis.delete(f"webhook:{webhook_id}")

        # 사용자 인덱스에서 제거
        self.redis.srem(f"user:{user_id}:webhooks", webhook_id)

        # 전송 기록 삭제 (SCAN 사용으로 블로킹 방지)
        cursor = 0
        while True:
            cursor, delivery_keys = self.redis.scan(cursor, match=f"webhook:{webhook_id}:delivery:*", count=100)
            if delivery_keys:
                self.redis.delete(*delivery_keys)
            if cursor == 0:
                break

        logger.info(f"Webhook deleted: {webhook_id} by user {user_id}")
        return True

    def _generate_signature(self, secret: str, payload: str) -> str:
        """HMAC-SHA256 서명 생성

        Args:
            secret: 비밀키
            payload: 페이로드 문자열

        Returns:
            HMAC 서명 (hex)
        """
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    async def _deliver_webhook(
        self,
        webhook: Webhook,
        event_type: WebhookEvent,
        payload: Dict[str, Any],
        retry_attempt: int = 0
    ) -> WebhookDelivery:
        """웹훅 전송 (내부 메서드)

        Args:
            webhook: 웹훅 객체
            event_type: 이벤트 타입
            payload: 페이로드
            retry_attempt: 재시도 횟수

        Returns:
            전송 기록
        """
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
            # 페이로드 JSON 직렬화
            payload_json = json.dumps(payload, ensure_ascii=False)

            # 헤더 구성
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "ChatbotWebhook/1.0",
                "X-Webhook-Event": event_type.value,
                "X-Webhook-Delivery": delivery_id,
                "X-Webhook-Timestamp": now.isoformat()
            }

            # HMAC 서명 추가
            if webhook.secret:
                signature = self._generate_signature(webhook.secret, payload_json)
                headers["X-Webhook-Signature"] = f"sha256={signature}"

            # HTTP POST 요청
            response = await self.http_client.post(
                webhook.url,
                content=payload_json,
                headers=headers,
                timeout=webhook.timeout_seconds
            )

            # 응답 처리
            delivery.status = "success" if response.status_code < 400 else "failed"
            delivery.response_status = response.status_code
            delivery.response_body = response.text[:500]  # 처음 500자만 저장
            delivery.delivered_at = datetime.now(timezone.utc)

            if delivery.status == "success":
                logger.info(
                    f"Webhook delivered successfully: {delivery_id} to {webhook.url} "
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

        # 전송 기록 저장
        self.redis.hset(
            f"webhook:{webhook.webhook_id}:delivery:{delivery_id}",
            mapping={
                "delivery_id": delivery_id,
                "webhook_id": webhook.webhook_id,
                "event_type": event_type.value,
                "payload": json.dumps(payload),
                "status": delivery.status,
                "response_status": str(delivery.response_status) if delivery.response_status else "",
                "response_body": delivery.response_body or "",
                "error_message": delivery.error_message or "",
                "created_at": delivery.created_at.isoformat(),
                "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else "",
                "retry_count": str(delivery.retry_count)
            }
        )

        # 전송 기록 유효기간 설정 (30일)
        self.redis.expire(f"webhook:{webhook.webhook_id}:delivery:{delivery_id}", 30 * 24 * 3600)

        # 통계 업데이트
        self.redis.hincrby(f"webhook:{webhook.webhook_id}", "total_deliveries", 1)
        if delivery.status == "success":
            self.redis.hincrby(f"webhook:{webhook.webhook_id}", "successful_deliveries", 1)
            self.redis.hset(f"webhook:{webhook.webhook_id}", "last_success_at", now.isoformat())
        else:
            self.redis.hincrby(f"webhook:{webhook.webhook_id}", "failed_deliveries", 1)
            self.redis.hset(f"webhook:{webhook.webhook_id}", "last_failure_at", now.isoformat())

        self.redis.hset(f"webhook:{webhook.webhook_id}", "last_delivery_at", now.isoformat())

        return delivery

    async def trigger_event(
        self,
        event_type: WebhookEvent,
        payload: Dict[str, Any]
    ) -> List[WebhookDelivery]:
        """이벤트 트리거 - 모든 해당 웹훅에 전송

        Args:
            event_type: 이벤트 타입
            payload: 페이로드

        Returns:
            전송 기록 목록
        """
        # 모든 웹훅 조회 (scan_iter 사용 - 블로킹 방지)
        webhook_keys = []
        for key in self.redis.scan_iter(match="webhook:*", count=100):
            key_str = key.decode() if isinstance(key, bytes) else key
            # delivery 키는 제외
            if ":delivery:" not in key_str:
                webhook_keys.append(key_str)

        deliveries = []
        if not webhook_keys:
            return deliveries

        # Pipeline으로 모든 웹훅 데이터를 배치 조회 (N+1 방지)
        pipe = self.redis.pipeline()
        for key in webhook_keys:
            pipe.get(key)
        webhook_data_list = pipe.execute()

        # 웹훅 처리
        for key, webhook_data in zip(webhook_keys, webhook_data_list):
            if not webhook_data:
                continue

            try:
                data = json.loads(webhook_data)
                webhook = Webhook(**data)

                if not webhook.is_active:
                    continue

                # 이벤트 구독 확인
                if event_type.value not in webhook.events:
                    continue

                # 비동기로 웹훅 전송 (재시도 로직 포함)
                delivery = await self._deliver_with_retry(webhook, event_type, payload)
                deliveries.append(delivery)
            except Exception as e:
                logger.error(f"Failed to process webhook {key}: {e}")
                continue

        return deliveries

    async def _deliver_with_retry(
        self,
        webhook: Webhook,
        event_type: WebhookEvent,
        payload: Dict[str, Any]
    ) -> WebhookDelivery:
        """재시도 로직을 포함한 웹훅 전송

        Args:
            webhook: 웹훅 객체
            event_type: 이벤트 타입
            payload: 페이로드

        Returns:
            최종 전송 기록
        """
        delivery = None

        for attempt in range(webhook.retry_count + 1):
            delivery = await self._deliver_webhook(webhook, event_type, payload, attempt)

            if delivery.status == "success":
                break

            # 재시도 대기 (지수 백오프: 1s, 2s, 4s, 8s, ...)
            if attempt < webhook.retry_count:
                wait_time = min(2 ** attempt, 60)  # 최대 60초
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
        """웹훅 테스트

        Args:
            webhook_id: 웹훅 ID
            event_type: 테스트할 이벤트 타입
            user_id: 요청 사용자 ID

        Returns:
            전송 기록

        Raises:
            ValueError: 웹훅을 찾을 수 없거나 권한이 없는 경우
        """
        webhook = await self.get_webhook(webhook_id)
        if not webhook:
            raise ValueError("웹훅을 찾을 수 없습니다")

        if webhook.created_by != user_id:
            raise ValueError("웹훅에 대한 권한이 없습니다")

        # 테스트 페이로드 생성
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

        Args:
            webhook_id: 웹훅 ID
            user_id: 요청 사용자 ID
            limit: 최대 개수

        Returns:
            전송 기록 목록
        """
        webhook = await self.get_webhook(webhook_id)
        if not webhook or webhook.created_by != user_id:
            return []

        # 전송 기록 키 조회 (SCAN 사용으로 블로킹 방지)
        delivery_keys = []
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match=f"webhook:{webhook_id}:delivery:*", count=100)
            delivery_keys.extend(keys)
            if cursor == 0:
                break
            if len(delivery_keys) >= limit:
                break

        if not delivery_keys:
            return []

        # Pipeline을 사용하여 모든 전송 기록을 일괄 조회 (N+1 → 1 쿼리)
        key_strs = [k.decode() if isinstance(k, bytes) else k for k in delivery_keys[:limit]]
        pipe = self.redis.pipeline()
        for key_str in key_strs:
            pipe.hgetall(key_str)
        data_list = pipe.execute()

        deliveries = []
        for data in data_list:
            if not data:
                continue

            def get_field(field_name: str, default=None):
                raw = data.get(field_name.encode()) or data.get(field_name)
                if raw is None:
                    return default
                return raw.decode() if isinstance(raw, bytes) else raw

            try:
                delivery = WebhookDelivery(
                    delivery_id=get_field("delivery_id"),
                    webhook_id=get_field("webhook_id"),
                    event_type=WebhookEvent(get_field("event_type")),
                    payload=json.loads(get_field("payload", "{}")),
                    status=get_field("status"),
                    response_status=int(get_field("response_status")) if get_field("response_status") else None,
                    response_body=get_field("response_body"),
                    error_message=get_field("error_message"),
                    created_at=datetime.fromisoformat(get_field("created_at")),
                    delivered_at=datetime.fromisoformat(get_field("delivered_at")) if get_field("delivered_at") else None,
                    retry_count=int(get_field("retry_count", 0))
                )
                deliveries.append(delivery)
            except Exception:
                continue

        # 최신순 정렬
        deliveries.sort(key=lambda d: d.created_at, reverse=True)
        return deliveries[:limit]

    async def cleanup(self):
        """리소스 정리"""
        await self.http_client.aclose()
