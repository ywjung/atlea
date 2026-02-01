"""
Audit Logging Middleware
자동 감사 로그 기록 미들웨어
"""
import time
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from loguru import logger

from ..audit import AuditAction
from ..utils.ip_utils import IPValidator


class AuditMiddleware(BaseHTTPMiddleware):
    """API 요청 자동 감사 로그 미들웨어"""

    def __init__(self, app, audit_logger=None):
        """
        Args:
            app: FastAPI application
            audit_logger: AuditLogger instance
        """
        super().__init__(app)
        self.audit_logger = audit_logger

        # 감사 로그 대상 경로 매핑
        self.action_mapping = {
            # 인증 (LOGIN은 API에서 직접 기록)
            ("POST", "/api/auth/logout"): AuditAction.LOGOUT,
            ("POST", "/api/auth/register"): AuditAction.REGISTER,
            ("PUT", "/api/auth/password"): AuditAction.PASSWORD_CHANGE,

            # 문서
            ("POST", "/api/documents/upload"): AuditAction.DOCUMENT_UPLOAD,
            ("DELETE", "/api/documents"): AuditAction.DOCUMENT_DELETE,
            ("GET", "/api/documents"): AuditAction.DOCUMENT_VIEW,

            # 채팅
            ("POST", "/api/chat"): AuditAction.CHAT_QUERY,

            # 그룹
            ("POST", "/api/groups"): AuditAction.GROUP_CREATE,
            ("PUT", "/api/groups"): AuditAction.GROUP_UPDATE,
            ("DELETE", "/api/groups"): AuditAction.GROUP_DELETE,

            # 설정
            ("GET", "/api/settings"): AuditAction.SETTINGS_VIEW,
            ("PUT", "/api/admin/settings"): AuditAction.SETTINGS_UPDATE,

            # 캐시
            ("DELETE", "/api/cache"): AuditAction.CACHE_CLEAR,
            ("GET", "/api/cache/stats"): AuditAction.CACHE_VIEW,
        }

    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 주소 추출 (IP 스푸핑 방지)"""
        # IPValidator를 사용하여 안전하게 IP 추출
        return IPValidator.get_client_ip(request, trust_proxy=True)

    def _get_redis_client(self, request: Request):
        """Redis 클라이언트 가져오기"""
        cache_mgr = getattr(request.app.state, 'cache_manager', None)
        if cache_mgr and hasattr(cache_mgr, 'redis'):
            return cache_mgr.redis
        return None

    def _get_user_info(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        """요청에서 사용자 정보 추출"""
        try:
            # app.state에서 사용자 정보 가져오기 (인증 미들웨어에서 설정)
            if hasattr(request.state, "user"):
                user = request.state.user
                return user.get("user_id"), user.get("username")

            redis_client = self._get_redis_client(request)

            # JWT 토큰에서 직접 추출
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                try:
                    from ..auth.utils import verify_token
                    user_data = verify_token(token, expected_type="access", redis_client=redis_client)
                    if user_data:
                        return user_data.get("user_id"), user_data.get("sub")  # sub = username
                except Exception:
                    pass  # 토큰 검증 실패 시 무시

            # 쿠키에서 토큰 추출
            token = request.cookies.get("access_token")
            if token:
                try:
                    from ..auth.utils import verify_token
                    user_data = verify_token(token, expected_type="access", redis_client=redis_client)
                    if user_data:
                        return user_data.get("user_id"), user_data.get("sub")  # sub = username
                except Exception:
                    pass  # 토큰 검증 실패 시 무시

            return None, None

        except Exception as e:
            logger.debug(f"Failed to extract user info: {e}")
            return None, None

    async def _get_resource_name(self, request: Request, response_body: Optional[dict] = None) -> Optional[str]:
        """리소스 이름 추출 (문서명, 그룹명 등)"""
        try:
            # 응답 본문에서 추출 (우선순위)
            if response_body and isinstance(response_body, dict):
                if "filename" in response_body:
                    return response_body["filename"]
                if "document_id" in response_body:
                    return response_body["document_id"]
                if "group_id" in response_body:
                    return response_body["group_id"]

            # URL 경로에서 추출
            path_parts = request.url.path.split("/")

            # 문서 작업 (ID 기반)
            if "/documents/" in request.url.path and len(path_parts) > 3:
                return path_parts[-1]  # 문서 ID 또는 이름

            # 그룹 작업
            if "/groups/" in request.url.path and len(path_parts) > 3:
                return path_parts[-1]  # 그룹 ID

            return None

        except Exception as e:
            logger.debug(f"Failed to extract resource name: {e}")
            return None

    def _should_audit(self, request: Request) -> bool:
        """감사 로그 대상 여부 확인"""
        # 정적 파일, health check 등은 제외
        exempt_prefixes = [
            "/static/",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/health"  # Health check는 감사 로그에서 제외
        ]

        return not any(request.url.path.startswith(prefix) for prefix in exempt_prefixes)

    async def dispatch(self, request: Request, call_next):
        """요청 처리 및 감사 로그 기록"""
        # Get audit_logger from app.state (initialized during startup)
        audit_logger = getattr(request.app.state, "audit_logger", None)

        # 감사 로그 비활성화 또는 제외 경로
        should_audit = self._should_audit(request)

        if not audit_logger or not should_audit:
            return await call_next(request)

        # 요청 시작 시간
        start_time = time.time()

        # 사용자 정보
        user_id, username = self._get_user_info(request)

        # IP 및 User-Agent
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent")

        # 작업 유형을 먼저 확인하여 불필요한 응답 본문 캡처 방지
        action_key = (request.method, request.url.path)
        action = self.action_mapping.get(action_key)

        # 패턴 매칭 (경로 파라미터 포함)
        if not action:
            for (method, path_pattern), mapped_action in self.action_mapping.items():
                if request.method == method and path_pattern in request.url.path:
                    action = mapped_action
                    break

        # 요청 처리
        response = await call_next(request)

        # 응답 본문 캡처 (감사 대상 액션이고 JSON 응답인 경우만)
        response_body = None
        if action and response.headers.get('content-type', '').startswith('application/json'):
            body_bytes = b""
            try:
                # 응답 본문 읽기
                async for chunk in response.body_iterator:
                    body_bytes += chunk

                # JSON 파싱
                import json
                response_body = json.loads(body_bytes.decode('utf-8'))

                # 새로운 응답 생성 (같은 본문으로)
                from starlette.responses import Response as StarletteResponse
                response = StarletteResponse(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
            except Exception as e:
                logger.debug(f"Failed to capture response body: {e}")

        # 응답 시간
        duration = time.time() - start_time

        # 감사 로그 기록
        if action:
            success = 200 <= response.status_code < 400

            # 리소스 이름 추출 (async)
            resource = await self._get_resource_name(request, response_body)

            # 상세 정보
            details = {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2)
            }

            # 쿼리 파라미터 (민감 정보 제외)
            if request.query_params:
                safe_params = {
                    k: v for k, v in request.query_params.items()
                    if k.lower() not in ["password", "token", "secret", "key"]
                }
                if safe_params:
                    details["query_params"] = safe_params

            # 로그 기록
            try:
                audit_logger.log(
                    action=action,
                    user_id=user_id,
                    username=username,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    resource=resource,
                    details=details,
                    success=success,
                    error_message=None if success else f"HTTP {response.status_code}"
                )
            except Exception as e:
                logger.error(f"Failed to record audit log: {e}", exc_info=True)

        return response
