"""IP Rate Limit Repository"""

from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.database.models.ip_rate_limit import IpRateLimit
from .base import BaseRepository


class IpRateLimitRepository(BaseRepository[IpRateLimit]):
    model = IpRateLimit

    async def check_rate_limit(
        self,
        ip_address: str,
        endpoint: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """Check rate limit. Returns (allowed, remaining, reset_seconds)."""
        now = datetime.now(timezone.utc)

        # Find existing record
        stmt = select(IpRateLimit).where(
            IpRateLimit.ip_address == ip_address,
            IpRateLimit.endpoint == endpoint,
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None or record.expires_at < now:
            # No record or expired — create/reset
            expires_at = now + timedelta(seconds=window_seconds)
            if record is None:
                record = IpRateLimit(
                    ip_address=ip_address,
                    endpoint=endpoint,
                    request_count=1,
                    window_start=now,
                    expires_at=expires_at,
                )
                self.session.add(record)
            else:
                record.request_count = 1
                record.window_start = now
                record.expires_at = expires_at
                record.blocked_until = None
                record.block_reason = None
            await self.session.flush()
            return True, max_requests - 1, window_seconds

        # Active window
        if record.request_count >= max_requests:
            reset_seconds = int((record.expires_at - now).total_seconds())
            return False, 0, max(reset_seconds, 1)

        record.request_count += 1
        await self.session.flush()
        remaining = max_requests - record.request_count
        reset_seconds = int((record.expires_at - now).total_seconds())
        return True, remaining, max(reset_seconds, 1)

    async def is_ip_blocked(self, ip_address: str) -> tuple[bool, int | None]:
        """Check if IP is blocked. Returns (blocked, remaining_seconds)."""
        now = datetime.now(timezone.utc)
        stmt = select(IpRateLimit).where(
            IpRateLimit.ip_address == ip_address,
            IpRateLimit.blocked_until != None,
            IpRateLimit.blocked_until > now,
        )
        result = await self.session.execute(stmt)
        record = result.scalars().first()

        if record and record.blocked_until:
            remaining = int((record.blocked_until - now).total_seconds())
            return True, remaining
        return False, None

    async def block_ip(
        self,
        ip_address: str,
        duration_seconds: int,
        reason: str,
        endpoint: str = "login",
    ) -> None:
        now = datetime.now(timezone.utc)
        blocked_until = now + timedelta(seconds=duration_seconds)

        stmt = select(IpRateLimit).where(
            IpRateLimit.ip_address == ip_address,
            IpRateLimit.endpoint == endpoint,
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            record.blocked_until = blocked_until
            record.block_reason = reason
        else:
            record = IpRateLimit(
                ip_address=ip_address,
                endpoint=endpoint,
                request_count=0,
                window_start=now,
                expires_at=blocked_until,
                blocked_until=blocked_until,
                block_reason=reason,
            )
            self.session.add(record)
        await self.session.flush()

    async def record_failed_attempt(
        self, ip_address: str, endpoint: str = "login"
    ) -> int:
        """Record a failed attempt and return total count in window."""
        now = datetime.now(timezone.utc)
        stmt = select(IpRateLimit).where(
            IpRateLimit.ip_address == ip_address,
            IpRateLimit.endpoint == endpoint,
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()

        if record and record.expires_at > now:
            record.request_count += 1
            await self.session.flush()
            return record.request_count
        else:
            if record:
                record.request_count = 1
                record.window_start = now
                record.expires_at = now + timedelta(seconds=1800)
                record.blocked_until = None
                record.block_reason = None
            else:
                record = IpRateLimit(
                    ip_address=ip_address,
                    endpoint=endpoint,
                    request_count=1,
                    window_start=now,
                    expires_at=now + timedelta(seconds=1800),
                )
                self.session.add(record)
            await self.session.flush()
            return 1

    async def delete_expired(self) -> int:
        now = datetime.now(timezone.utc)
        stmt = delete(IpRateLimit).where(
            IpRateLimit.expires_at < now,
            (IpRateLimit.blocked_until == None) | (IpRateLimit.blocked_until < now),
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def reset_for_ip(self, ip_address: str, endpoint: str | None = None) -> int:
        if endpoint:
            stmt = delete(IpRateLimit).where(
                IpRateLimit.ip_address == ip_address,
                IpRateLimit.endpoint == endpoint,
            )
        else:
            stmt = delete(IpRateLimit).where(
                IpRateLimit.ip_address == ip_address,
            )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
