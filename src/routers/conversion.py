"""
Document Conversion Router

Provides document format conversion services (HTML/Markdown to HWPX).
"""

import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from loguru import logger
import httpx

from ..auth.middleware import get_current_active_user

router = APIRouter(prefix="/api/convert", tags=["Conversion"])


# ==================== Request Model ====================

class HwpxConversionRequest(BaseModel):
    """HWPX 변환 요청"""
    content: str = Field(..., description="변환할 HTML 또는 Markdown 내용")
    content_type: str = Field(default="html", description="내용 타입: 'html' 또는 'markdown'")
    filename: Optional[str] = Field(default=None, description="출력 파일명 (선택사항)")


# ==================== Endpoints ====================

@router.post("/hwpx")
async def convert_to_hwpx(
    request: HwpxConversionRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    HTML/Markdown을 HWPX 형식으로 변환

    - 인증 필요 (로그인한 사용자만)
    - Java document-service에 프록시 요청
    - HWPX 파일을 바이너리로 반환
    """
    try:
        logger.info(f"📄 HWPX 변환 요청: content_type={request.content_type}, 길이={len(request.content)}")

        # Java 서비스 URL
        java_service_url = os.getenv("DOCUMENT_SERVICE_URL", "http://localhost:8081")

        # 엔드포인트 선택
        if request.content_type == "markdown":
            endpoint = f"{java_service_url}/api/conversion/markdown-to-hwpx"
            payload = {
                "markdownContent": request.content,
                "filename": request.filename
            }
        else:  # html
            endpoint = f"{java_service_url}/api/conversion/html-to-hwpx"
            payload = {
                "htmlContent": request.content,
                "filename": request.filename
            }

        # Java 서비스에 요청
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"❌ Java 서비스 오류: {response.status_code} - {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"HWPX 변환 실패: {error_detail}"
                )

            # 파일명 추출 (Content-Disposition 헤더에서)
            content_disposition = response.headers.get("content-disposition", "")
            filename = request.filename or "document.hwpx"
            if "filename=" in content_disposition:
                # filename*=UTF-8''encoded_name 형식 처리
                import urllib.parse
                parts = content_disposition.split("filename=")
                if len(parts) > 1:
                    filename_part = parts[1].strip('"').strip("'")
                    try:
                        filename = urllib.parse.unquote(filename_part)
                    except Exception:
                        pass

            if not filename.endswith(".hwpx"):
                filename += ".hwpx"

            logger.success(f"✅ HWPX 변환 완료: {filename}, {len(response.content)} bytes")

            # HWPX 파일 반환
            return Response(
                content=response.content,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(len(response.content))
                }
            )

    except httpx.TimeoutException:
        logger.error("❌ Java 서비스 타임아웃")
        raise HTTPException(
            status_code=504,
            detail="HWPX 변환 서비스 응답 시간 초과"
        )
    except httpx.ConnectError:
        logger.error("❌ Java 서비스 연결 실패")
        raise HTTPException(
            status_code=503,
            detail="HWPX 변환 서비스에 연결할 수 없습니다. 서비스가 실행 중인지 확인하세요."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ HWPX 변환 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"HWPX 변환 중 오류가 발생했습니다: {str(e)}"
        )
