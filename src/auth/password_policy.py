"""Password Complexity Policy

비밀번호 복잡도 정책 검증 및 요구사항 정의.
"""

import re
from typing import List, Tuple


class PasswordPolicy:
    """비밀번호 정책 검증기

    OWASP 권장사항을 기반으로 한 비밀번호 복잡도 정책.
    """

    # 정책 설정
    MIN_LENGTH = 8
    MAX_LENGTH = 128
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGIT = True
    REQUIRE_SPECIAL = True

    # 특수문자 목록
    SPECIAL_CHARACTERS = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"

    @classmethod
    def validate(cls, password: str) -> Tuple[bool, List[str]]:
        """비밀번호 복잡도 검증

        Args:
            password: 검증할 비밀번호

        Returns:
            Tuple[bool, List[str]]: (검증 통과 여부, 오류 메시지 목록)
        """
        errors = []

        # 1. 길이 검사
        if len(password) < cls.MIN_LENGTH:
            errors.append(f"비밀번호는 최소 {cls.MIN_LENGTH}자 이상이어야 합니다")

        if len(password) > cls.MAX_LENGTH:
            errors.append(f"비밀번호는 최대 {cls.MAX_LENGTH}자를 초과할 수 없습니다")

        # 2. 대문자 포함 검사
        if cls.REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            errors.append("비밀번호는 최소 1개의 대문자를 포함해야 합니다")

        # 3. 소문자 포함 검사
        if cls.REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            errors.append("비밀번호는 최소 1개의 소문자를 포함해야 합니다")

        # 4. 숫자 포함 검사
        if cls.REQUIRE_DIGIT and not re.search(r'\d', password):
            errors.append("비밀번호는 최소 1개의 숫자를 포함해야 합니다")

        # 5. 특수문자 포함 검사
        if cls.REQUIRE_SPECIAL:
            special_pattern = f'[{re.escape(cls.SPECIAL_CHARACTERS)}]'
            if not re.search(special_pattern, password):
                errors.append(f"비밀번호는 최소 1개의 특수문자({cls.SPECIAL_CHARACTERS})를 포함해야 합니다")

        # 6. 공백 포함 금지
        if ' ' in password:
            errors.append("비밀번호는 공백을 포함할 수 없습니다")

        return (len(errors) == 0, errors)

    @classmethod
    def get_requirements(cls) -> str:
        """비밀번호 요구사항 문자열 반환

        Returns:
            비밀번호 정책 요구사항 설명
        """
        requirements = [
            f"• {cls.MIN_LENGTH}자 이상 {cls.MAX_LENGTH}자 이하"
        ]

        if cls.REQUIRE_UPPERCASE:
            requirements.append("• 최소 1개의 대문자 (A-Z)")

        if cls.REQUIRE_LOWERCASE:
            requirements.append("• 최소 1개의 소문자 (a-z)")

        if cls.REQUIRE_DIGIT:
            requirements.append("• 최소 1개의 숫자 (0-9)")

        if cls.REQUIRE_SPECIAL:
            requirements.append(f"• 최소 1개의 특수문자 ({cls.SPECIAL_CHARACTERS})")

        requirements.append("• 공백 불가")

        return "\n".join(requirements)

    @classmethod
    def is_strong_password(cls, password: str) -> bool:
        """비밀번호가 강력한지 확인 (편의 메서드)

        Args:
            password: 검증할 비밀번호

        Returns:
            검증 통과 여부
        """
        is_valid, _ = cls.validate(password)
        return is_valid


def validate_password_strength(password: str) -> str:
    """비밀번호 강도 검증 (Pydantic validator 용)

    Args:
        password: 검증할 비밀번호

    Returns:
        검증된 비밀번호

    Raises:
        ValueError: 비밀번호가 정책을 만족하지 않을 때
    """
    is_valid, errors = PasswordPolicy.validate(password)

    if not is_valid:
        error_message = "비밀번호가 복잡도 요구사항을 만족하지 않습니다:\n" + "\n".join(errors)
        raise ValueError(error_message)

    return password


# 일반적인 약한 비밀번호 목록 (선택적 사용)
COMMON_WEAK_PASSWORDS = {
    "password", "Password1!", "12345678", "Qwerty123!",
    "Admin123!", "Welcome1!", "P@ssw0rd", "Password123!",
    "Abcd1234!", "Test1234!", "User1234!"
}


def is_common_password(password: str) -> bool:
    """일반적으로 사용되는 약한 비밀번호인지 확인

    Args:
        password: 확인할 비밀번호

    Returns:
        약한 비밀번호 여부
    """
    return password in COMMON_WEAK_PASSWORDS
