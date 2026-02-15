"""Image-based Math CAPTCHA Service

내부망에서 사용 가능한 자체 CAPTCHA 시스템.
인터넷 연결 없이 이미지 기반 수학 문제로 봇 방지.
"""

import random
import uuid
import io
import base64
from typing import Optional
from datetime import datetime, timedelta, timezone
from loguru import logger

from PIL import Image, ImageDraw, ImageFont, ImageFilter


class SimpleCaptchaService:
    """이미지 기반 수학 문제 CAPTCHA 서비스 (내부망 사용)

    Features:
    - 인터넷 연결 불필요
    - 이미지 기반 덧셈/뺄셈 문제
    - 노이즈, 왜곡으로 OCR 방지
    - PostgreSQL 기반 답안 저장 (5분 유효)
    - 재사용 방지
    """

    # CAPTCHA 이미지 설정
    WIDTH = 280
    HEIGHT = 80
    FONT_SIZE = 32

    def __init__(self):
        """초기화

        Args:
        """
        pass

    def is_enabled(self, action: str = "login") -> bool:
        """CAPTCHA 활성화 여부 확인 (PostgreSQL 설정)"""
        try:
            from ..services.config_service import config_get_sync

            if action == "register":
                key = "config:captcha_register_enabled"
            else:
                key = "config:captcha_login_enabled"

            enabled_str = config_get_sync(key)
            if enabled_str is not None:
                return enabled_str == "true"

            return False

        except Exception as e:
            logger.warning(f"Failed to check CAPTCHA enabled status for {action}: {e}")
            return False

    def _generate_captcha_image(self, text: str) -> str:
        """CAPTCHA 이미지 생성"""
        try:
            image = Image.new('RGB', (self.WIDTH, self.HEIGHT), color='white')
            draw = ImageDraw.Draw(image)

            # 배경 노이즈 (랜덤 선)
            for _ in range(5):
                x1 = random.randint(0, self.WIDTH)
                y1 = random.randint(0, self.HEIGHT)
                x2 = random.randint(0, self.WIDTH)
                y2 = random.randint(0, self.HEIGHT)
                color = (
                    random.randint(180, 220),
                    random.randint(180, 220),
                    random.randint(180, 220)
                )
                draw.line([(x1, y1), (x2, y2)], fill=color, width=1)

            # 배경 노이즈 (랜덤 점)
            for _ in range(30):
                x = random.randint(0, self.WIDTH)
                y = random.randint(0, self.HEIGHT)
                color = (
                    random.randint(150, 200),
                    random.randint(150, 200),
                    random.randint(150, 200)
                )
                draw.point((x, y), fill=color)

            # 폰트 설정
            try:
                font_paths = [
                    '/System/Library/Fonts/Helvetica.ttc',
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                    'C:\\Windows\\Fonts\\arial.ttf',
                ]
                font = None
                for font_path in font_paths:
                    try:
                        font = ImageFont.truetype(font_path, self.FONT_SIZE)
                        break
                    except (OSError, IOError):
                        continue

                if font is None:
                    font = ImageFont.load_default()
                    logger.warning("Using default font for CAPTCHA")
            except Exception as e:
                logger.warning(f"Error loading font: {e}, using default")
                font = ImageFont.load_default()

            # 텍스트 위치 계산
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            margin = 20
            available_width = self.WIDTH - (margin * 2)
            char_spacing = 2 if text_width > available_width else random.randint(2, 5)

            x = margin
            y = (self.HEIGHT - text_height) // 2

            # 텍스트를 문자별로 그리기
            current_x = x
            for i, char in enumerate(text):
                angle = random.randint(-12, 12)
                y_offset = random.randint(-5, 5)
                color = (
                    random.randint(0, 60),
                    random.randint(0, 60),
                    random.randint(0, 60)
                )

                char_bbox = draw.textbbox((0, 0), char, font=font)
                char_width = char_bbox[2] - char_bbox[0]
                char_height = char_bbox[3] - char_bbox[1]

                char_image = Image.new('RGBA', (char_width + 30, char_height + 30), (255, 255, 255, 0))
                char_draw = ImageDraw.Draw(char_image)
                char_draw.text((15, 15), char, font=font, fill=color)

                char_image = char_image.rotate(angle, expand=True, fillcolor=(255, 255, 255, 0))
                image.paste(char_image, (current_x - 15, y + y_offset - 15), char_image)
                current_x += char_width + char_spacing

            image = image.filter(ImageFilter.GaussianBlur(radius=0.5))

            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return f"data:image/png;base64,{image_base64}"

        except Exception as e:
            logger.error(f"Failed to generate CAPTCHA image: {e}", exc_info=True)
            return ""

    def generate_captcha(self) -> dict:
        """수학 문제 CAPTCHA 생성"""
        try:
            num1 = random.randint(1, 20)
            num2 = random.randint(1, 20)
            operator = random.choice(['+', '-'])

            if operator == '+':
                answer = num1 + num2
                question = f"{num1} + {num2} = ?"
            else:
                if num1 < num2:
                    num1, num2 = num2, num1
                answer = num1 - num2
                question = f"{num1} - {num2} = ?"

            captcha_id = str(uuid.uuid4())

            # PostgreSQL에 답 저장 (5분 유효)
            from ..database.connection import SyncSessionFactory
            from ..database.models.captcha_challenge import CaptchaChallenge

            expires_at = datetime.now(timezone.utc) + timedelta(seconds=300)
            with SyncSessionFactory() as session:
                challenge = CaptchaChallenge(
                    id=uuid.UUID(captcha_id),
                    answer=str(answer),
                    expires_at=expires_at,
                )
                session.add(challenge)
                session.commit()

            image_data = self._generate_captcha_image(question)

            logger.debug(f"Generated image CAPTCHA: {question} (id={captcha_id})")

            return {
                "captcha_id": captcha_id,
                "image": image_data
            }

        except Exception as e:
            logger.error(f"Failed to generate CAPTCHA: {e}", exc_info=True)
            return {
                "captcha_id": "",
                "image": ""
            }

    async def verify_captcha(
        self,
        captcha_id: str,
        user_answer: str
    ) -> tuple[bool, Optional[str]]:
        """CAPTCHA 답 검증"""
        if not self.is_enabled():
            logger.debug("CAPTCHA is disabled, skipping verification")
            return True, None

        if not captcha_id or not user_answer:
            logger.warning("CAPTCHA ID or answer is missing")
            return False, "CAPTCHA 답변이 필요합니다"

        try:
            from ..database.connection import AsyncSessionFactory
            from ..repositories.captcha_repository import CaptchaRepository

            async with AsyncSessionFactory() as session:
                repo = CaptchaRepository(session)
                result = await repo.verify_and_consume(
                    uuid.UUID(captcha_id), user_answer.strip()
                )
                await session.commit()

            if result is None:
                logger.warning(f"CAPTCHA expired or not found: {captcha_id}")
                return False, "CAPTCHA가 만료되었습니다. 새로고침 후 다시 시도하세요"

            if result is False:
                logger.warning(f"CAPTCHA answer mismatch for {captcha_id}")
                return False, "CAPTCHA 답변이 틀렸습니다"

            logger.info(f"CAPTCHA verification successful: {captcha_id}")
            return True, None

        except Exception as e:
            logger.error(f"CAPTCHA verification error: {e}", exc_info=True)
            return False, "CAPTCHA 검증 중 오류가 발생했습니다"


# CAPTCHA 설정 헬퍼 함수
def set_captcha_enabled(
    login_enabled: bool = None,
    register_enabled: bool = None
) -> bool:
    """CAPTCHA 활성화 상태 설정 (PostgreSQL)"""
    try:
        from ..services.config_service import config_set_sync

        if login_enabled is not None:
            config_set_sync(
                "config:captcha_login_enabled",
                "true" if login_enabled else "false",
                "boolean",
            )
            logger.info(f"CAPTCHA login enabled status set to: {login_enabled}")

        if register_enabled is not None:
            config_set_sync(
                "config:captcha_register_enabled",
                "true" if register_enabled else "false",
                "boolean",
            )
            logger.info(f"CAPTCHA register enabled status set to: {register_enabled}")

        return True

    except Exception as e:
        logger.error(f"Failed to set CAPTCHA enabled status: {e}")
        return False


def get_captcha_config() -> dict:
    """CAPTCHA 설정 조회 (PostgreSQL)"""
    try:
        from ..services.config_service import config_get_sync

        login_str = config_get_sync("config:captcha_login_enabled")
        register_str = config_get_sync("config:captcha_register_enabled")

        login_enabled = login_str == "true" if login_str else False
        register_enabled = register_str == "true" if register_str else False

        return {
            "login_enabled": login_enabled,
            "register_enabled": register_enabled,
            "type": "image_math",
            "configured": True
        }

    except Exception as e:
        logger.error(f"Failed to get CAPTCHA config: {e}")
        return {
            "login_enabled": False,
            "register_enabled": False,
            "type": "image_math",
            "configured": False
        }
