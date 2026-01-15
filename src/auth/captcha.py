"""Image-based Math CAPTCHA Service

내부망에서 사용 가능한 자체 CAPTCHA 시스템.
인터넷 연결 없이 이미지 기반 수학 문제로 봇 방지.
"""

import random
import uuid
import io
import base64
from typing import Optional
from redis import Redis
from loguru import logger

from PIL import Image, ImageDraw, ImageFont, ImageFilter


class SimpleCaptchaService:
    """이미지 기반 수학 문제 CAPTCHA 서비스 (내부망 사용)

    Features:
    - 인터넷 연결 불필요
    - 이미지 기반 덧셈/뺄셈 문제
    - 노이즈, 왜곡으로 OCR 방지
    - Redis 기반 답안 저장 (5분 유효)
    - 재사용 방지
    """

    # CAPTCHA 이미지 설정
    WIDTH = 280
    HEIGHT = 80
    FONT_SIZE = 32

    def __init__(self, redis_client: Redis):
        """초기화

        Args:
            redis_client: Redis 클라이언트 인스턴스
        """
        self.redis = redis_client

    def is_enabled(self, action: str = "login") -> bool:
        """CAPTCHA 활성화 여부 확인 (Redis 설정)

        Args:
            action: 'login' 또는 'register'

        Returns:
            bool: CAPTCHA 활성화 여부
        """
        try:
            # action별로 다른 Redis 키 확인
            if action == "register":
                key = "config:captcha_register_enabled"
            else:  # login이 기본값
                key = "config:captcha_login_enabled"

            enabled_str = self.redis.get(key)
            if enabled_str is not None:
                return enabled_str.decode() == "true"

            # 기본값: 비활성화 (관리자가 명시적으로 활성화해야 함)
            return False

        except Exception as e:
            logger.warning(f"Failed to check CAPTCHA enabled status for {action}: {e}")
            # Redis 오류 시 안전을 위해 비활성화
            return False

    def _generate_captcha_image(self, text: str) -> str:
        """CAPTCHA 이미지 생성

        Args:
            text: CAPTCHA에 표시할 텍스트 (예: "3 + 5 = ?")

        Returns:
            Base64로 인코딩된 이미지 데이터 (data:image/png;base64,...)
        """
        try:
            # 이미지 생성 (배경색: 흰색)
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

            # 폰트 설정 (기본 폰트 사용)
            try:
                # 시스템 폰트 시도 (macOS, Linux, Windows)
                font_paths = [
                    '/System/Library/Fonts/Helvetica.ttc',  # macOS
                    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Linux
                    'C:\\Windows\\Fonts\\arial.ttf',  # Windows
                ]
                font = None
                for font_path in font_paths:
                    try:
                        font = ImageFont.truetype(font_path, self.FONT_SIZE)
                        break
                    except (OSError, IOError):
                        continue

                if font is None:
                    # 시스템 폰트를 찾지 못하면 기본 폰트 사용
                    font = ImageFont.load_default()
                    # 기본 폰트는 작으므로 텍스트 크기 조정
                    logger.warning("Using default font for CAPTCHA")
            except Exception as e:
                logger.warning(f"Error loading font: {e}, using default")
                font = ImageFont.load_default()

            # 텍스트 위치 계산 (중앙 정렬, 좌우 여백 20px 확보)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # 좌우 여백 20px씩 확보
            margin = 20
            available_width = self.WIDTH - (margin * 2)

            # 텍스트가 너무 길면 문자 간격 조정
            char_spacing = 2 if text_width > available_width else random.randint(2, 5)

            x = margin
            y = (self.HEIGHT - text_height) // 2

            # 텍스트를 문자별로 그리기 (각 문자마다 약간씩 회전)
            current_x = x
            for i, char in enumerate(text):
                # 랜덤 회전 각도 (-12 ~ 12도로 약간 줄임)
                angle = random.randint(-12, 12)

                # 랜덤 Y 오프셋 (-5 ~ 5픽셀)
                y_offset = random.randint(-5, 5)

                # 문자 색상 (어두운 색)
                color = (
                    random.randint(0, 60),
                    random.randint(0, 60),
                    random.randint(0, 60)
                )

                # 임시 이미지에 문자 그리기
                char_bbox = draw.textbbox((0, 0), char, font=font)
                char_width = char_bbox[2] - char_bbox[0]
                char_height = char_bbox[3] - char_bbox[1]

                # 문자 이미지 생성 (여유 공간 더 확보)
                char_image = Image.new('RGBA', (char_width + 30, char_height + 30), (255, 255, 255, 0))
                char_draw = ImageDraw.Draw(char_image)
                char_draw.text((15, 15), char, font=font, fill=color)

                # 회전
                char_image = char_image.rotate(angle, expand=True, fillcolor=(255, 255, 255, 0))

                # 원본 이미지에 붙이기
                image.paste(char_image, (current_x - 15, y + y_offset - 15), char_image)

                current_x += char_width + char_spacing

            # 약간의 블러 효과 (OCR 방지)
            image = image.filter(ImageFilter.GaussianBlur(radius=0.5))

            # Base64 인코딩
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return f"data:image/png;base64,{image_base64}"

        except Exception as e:
            logger.error(f"Failed to generate CAPTCHA image: {e}", exc_info=True)
            # 실패 시 빈 이미지 반환
            return ""

    def generate_captcha(self) -> dict:
        """수학 문제 CAPTCHA 생성

        Returns:
            {
                "captcha_id": str,  # CAPTCHA 고유 ID
                "image": str        # Base64 인코딩된 이미지 데이터
            }
        """
        try:
            # 간단한 덧셈/뺄셈 문제 생성
            num1 = random.randint(1, 20)
            num2 = random.randint(1, 20)
            operator = random.choice(['+', '-'])

            if operator == '+':
                answer = num1 + num2
                question = f"{num1} + {num2} = ?"
            else:
                # 음수 방지
                if num1 < num2:
                    num1, num2 = num2, num1
                answer = num1 - num2
                question = f"{num1} - {num2} = ?"

            # CAPTCHA ID 생성
            captcha_id = str(uuid.uuid4())

            # Redis에 답 저장 (5분 유효)
            self.redis.setex(
                f"captcha:{captcha_id}",
                300,  # 5분
                str(answer)
            )

            # 이미지 생성
            image_data = self._generate_captcha_image(question)

            logger.debug(f"Generated image CAPTCHA: {question} (id={captcha_id})")

            return {
                "captcha_id": captcha_id,
                "image": image_data
            }

        except Exception as e:
            logger.error(f"Failed to generate CAPTCHA: {e}", exc_info=True)
            # 실패 시 기본 CAPTCHA 반환
            return {
                "captcha_id": "",
                "image": ""
            }

    async def verify_captcha(
        self,
        captcha_id: str,
        user_answer: str
    ) -> tuple[bool, Optional[str]]:
        """CAPTCHA 답 검증

        Args:
            captcha_id: CAPTCHA 고유 ID
            user_answer: 사용자가 입력한 답

        Returns:
            (success, error_message) tuple
            - success: 검증 성공 여부
            - error_message: 실패 시 에러 메시지, 성공 시 None
        """
        # CAPTCHA 비활성화 상태면 항상 성공
        if not self.is_enabled():
            logger.debug("CAPTCHA is disabled, skipping verification")
            return True, None

        # 입력값 확인
        if not captcha_id or not user_answer:
            logger.warning("CAPTCHA ID or answer is missing")
            return False, "CAPTCHA 답변이 필요합니다"

        try:
            # Redis에서 정답 조회
            stored_answer = self.redis.get(f"captcha:{captcha_id}")

            if not stored_answer:
                logger.warning(f"CAPTCHA expired or not found: {captcha_id}")
                return False, "CAPTCHA가 만료되었습니다. 새로고침 후 다시 시도하세요"

            stored_answer = stored_answer.decode()

            # 답 비교
            if user_answer.strip() != stored_answer:
                logger.warning(
                    f"CAPTCHA answer mismatch: "
                    f"expected={stored_answer}, got={user_answer}"
                )
                return False, "CAPTCHA 답변이 틀렸습니다"

            # 사용한 CAPTCHA 삭제 (재사용 방지)
            self.redis.delete(f"captcha:{captcha_id}")

            logger.info(f"CAPTCHA verification successful: {captcha_id}")
            return True, None

        except Exception as e:
            logger.error(f"CAPTCHA verification error: {e}", exc_info=True)
            return False, "CAPTCHA 검증 중 오류가 발생했습니다"


# CAPTCHA 설정 헬퍼 함수
def set_captcha_enabled(
    redis_client: Redis,
    login_enabled: bool = None,
    register_enabled: bool = None
) -> bool:
    """CAPTCHA 활성화 상태 설정

    Args:
        redis_client: Redis 클라이언트
        login_enabled: 로그인 CAPTCHA 활성화 여부 (None이면 변경 안 함)
        register_enabled: 회원가입 CAPTCHA 활성화 여부 (None이면 변경 안 함)

    Returns:
        성공 여부
    """
    try:
        if login_enabled is not None:
            redis_client.set(
                "config:captcha_login_enabled",
                "true" if login_enabled else "false"
            )
            logger.info(f"CAPTCHA login enabled status set to: {login_enabled}")

        if register_enabled is not None:
            redis_client.set(
                "config:captcha_register_enabled",
                "true" if register_enabled else "false"
            )
            logger.info(f"CAPTCHA register enabled status set to: {register_enabled}")

        return True

    except Exception as e:
        logger.error(f"Failed to set CAPTCHA enabled status: {e}")
        return False


def get_captcha_config(redis_client: Redis) -> dict:
    """CAPTCHA 설정 조회

    Args:
        redis_client: Redis 클라이언트

    Returns:
        {
            "login_enabled": bool,
            "register_enabled": bool,
            "type": "image_math",
            "configured": bool
        }
    """
    try:
        login_str = redis_client.get("config:captcha_login_enabled")
        register_str = redis_client.get("config:captcha_register_enabled")

        login_enabled = login_str.decode() == "true" if login_str else False
        register_enabled = register_str.decode() == "true" if register_str else False

        return {
            "login_enabled": login_enabled,
            "register_enabled": register_enabled,
            "type": "image_math",
            "configured": True  # 자체 CAPTCHA는 항상 설정됨
        }

    except Exception as e:
        logger.error(f"Failed to get CAPTCHA config: {e}")
        return {
            "login_enabled": False,
            "register_enabled": False,
            "type": "image_math",
            "configured": False
        }
