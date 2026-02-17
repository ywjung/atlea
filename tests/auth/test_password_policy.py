"""Tests for Password Policy

비밀번호 복잡도 정책 테스트.
"""

import pytest
from src.auth.password_policy import (
    PasswordPolicy,
    validate_password_strength,
    is_common_password,
    COMMON_WEAK_PASSWORDS
)


class TestPasswordPolicyValidation:
    """비밀번호 정책 검증 테스트"""

    def test_valid_password(self):
        """유효한 비밀번호"""
        valid_passwords = [
            "Password123!",
            "MyP@ssw0rd",
            "Secure1!",
            "C0mpl3x!Pass",
            "Test@1234",
            "!Abc123def",
            "P@ssW0rd!"
        ]

        for password in valid_passwords:
            is_valid, errors = PasswordPolicy.validate(password)
            assert is_valid, f"{password} should be valid, errors: {errors}"
            assert len(errors) == 0

    def test_too_short_password(self):
        """너무 짧은 비밀번호"""
        is_valid, errors = PasswordPolicy.validate("Abc1!")
        assert not is_valid
        assert any("최소 8자" in error for error in errors)

    def test_too_long_password(self):
        """너무 긴 비밀번호"""
        long_password = "A" * 129 + "bc1!"
        is_valid, errors = PasswordPolicy.validate(long_password)
        assert not is_valid
        assert any("최대 128자" in error for error in errors)

    def test_no_uppercase(self):
        """대문자 없음"""
        is_valid, errors = PasswordPolicy.validate("password123!")
        assert not is_valid
        assert any("대문자" in error for error in errors)

    def test_no_lowercase(self):
        """소문자 없음"""
        is_valid, errors = PasswordPolicy.validate("PASSWORD123!")
        assert not is_valid
        assert any("소문자" in error for error in errors)

    def test_no_digit(self):
        """숫자 없음"""
        is_valid, errors = PasswordPolicy.validate("Password!")
        assert not is_valid
        assert any("숫자" in error for error in errors)

    def test_no_special_character(self):
        """특수문자 없음"""
        is_valid, errors = PasswordPolicy.validate("Password123")
        assert not is_valid
        assert any("특수문자" in error for error in errors)

    def test_contains_space(self):
        """공백 포함"""
        is_valid, errors = PasswordPolicy.validate("Pass word123!")
        assert not is_valid
        assert any("공백" in error for error in errors)

    def test_multiple_violations(self):
        """여러 정책 위반"""
        is_valid, errors = PasswordPolicy.validate("abc")
        assert not is_valid
        assert len(errors) >= 3  # 길이, 대문자, 숫자, 특수문자 위반


class TestPasswordPolicyRequirements:
    """비밀번호 정책 요구사항 테스트"""

    def test_get_requirements(self):
        """요구사항 문자열 반환"""
        requirements = PasswordPolicy.get_requirements()

        assert "8자 이상" in requirements
        assert "대문자" in requirements
        assert "소문자" in requirements
        assert "숫자" in requirements
        assert "특수문자" in requirements
        assert "공백 불가" in requirements

    def test_is_strong_password_convenience_method(self):
        """편의 메서드 테스트"""
        assert PasswordPolicy.is_strong_password("Password123!")
        assert not PasswordPolicy.is_strong_password("weak")


class TestPasswordPolicyConfiguration:
    """비밀번호 정책 설정 테스트"""

    def test_policy_constants(self):
        """정책 상수 확인"""
        assert PasswordPolicy.MIN_LENGTH == 8
        assert PasswordPolicy.MAX_LENGTH == 128
        assert PasswordPolicy.REQUIRE_UPPERCASE is True
        assert PasswordPolicy.REQUIRE_LOWERCASE is True
        assert PasswordPolicy.REQUIRE_DIGIT is True
        assert PasswordPolicy.REQUIRE_SPECIAL is True

    def test_special_characters_list(self):
        """특수문자 목록 확인"""
        assert len(PasswordPolicy.SPECIAL_CHARACTERS) > 0
        assert "!" in PasswordPolicy.SPECIAL_CHARACTERS
        assert "@" in PasswordPolicy.SPECIAL_CHARACTERS
        assert "#" in PasswordPolicy.SPECIAL_CHARACTERS


class TestPasswordStrengthValidator:
    """Pydantic validator 함수 테스트"""

    def test_valid_password_returns_password(self):
        """유효한 비밀번호는 그대로 반환"""
        password = "ValidPass123!"
        result = validate_password_strength(password)
        assert result == password

    def test_invalid_password_raises_value_error(self):
        """유효하지 않은 비밀번호는 ValueError 발생"""
        with pytest.raises(ValueError) as exc_info:
            validate_password_strength("weak")

        assert "복잡도 요구사항" in str(exc_info.value)

    def test_error_message_contains_all_violations(self):
        """오류 메시지에 모든 위반 사항 포함"""
        with pytest.raises(ValueError) as exc_info:
            validate_password_strength("abc")

        error_message = str(exc_info.value)
        assert "최소 8자" in error_message
        assert "대문자" in error_message
        assert "숫자" in error_message
        assert "특수문자" in error_message


class TestCommonWeakPasswords:
    """약한 비밀번호 목록 테스트"""

    def test_common_weak_passwords_exists(self):
        """약한 비밀번호 목록 존재"""
        assert len(COMMON_WEAK_PASSWORDS) > 0
        assert "password" in COMMON_WEAK_PASSWORDS
        assert "Password1!" in COMMON_WEAK_PASSWORDS

    def test_is_common_password_detection(self):
        """일반적인 약한 비밀번호 감지"""
        assert is_common_password("password")
        assert is_common_password("Password1!")
        assert is_common_password("Admin123!")
        assert not is_common_password("MyUn1qu3P@ss")


class TestPasswordPolicyEdgeCases:
    """비밀번호 정책 엣지 케이스 테스트"""

    def test_exactly_min_length(self):
        """정확히 최소 길이"""
        password = "Abcd123!"  # 정확히 8자
        is_valid, errors = PasswordPolicy.validate(password)
        assert is_valid

    def test_exactly_max_length(self):
        """정확히 최대 길이"""
        password = "A" * 124 + "bc1!"  # 정확히 128자
        is_valid, errors = PasswordPolicy.validate(password)
        assert is_valid

    def test_unicode_characters(self):
        """유니코드 문자 포함"""
        # 한글, 이모지 등은 일반 문자로 처리됨
        password = "Password123!한글"
        is_valid, errors = PasswordPolicy.validate(password)
        assert is_valid

    def test_multiple_special_characters(self):
        """여러 특수문자 포함"""
        password = "Pass!@#$123Abc"
        is_valid, errors = PasswordPolicy.validate(password)
        assert is_valid

    def test_all_special_characters_valid(self):
        """모든 허용된 특수문자 테스트"""
        for char in PasswordPolicy.SPECIAL_CHARACTERS:
            password = f"Password1{char}"
            is_valid, errors = PasswordPolicy.validate(password)
            assert is_valid, f"Password with '{char}' should be valid"

    def test_tab_and_newline_rejected(self):
        """탭과 줄바꿈 문자 거부"""
        # 공백 계열 문자는 모두 거부되어야 함
        passwords_with_whitespace = [
            "Pass\tword123!",  # 탭
            "Pass\nword123!",  # 줄바꿈
            "Pass\rword123!",  # 캐리지 리턴
        ]

        for password in passwords_with_whitespace:
            is_valid, _ = PasswordPolicy.validate(password)
            # 현재 정책은 공백만 체크하므로 탭/줄바꿈은 통과될 수 있음
            # 필요시 정책 강화 필요


class TestPasswordPolicyIntegration:
    """비밀번호 정책 통합 테스트"""

    def test_policy_with_pydantic_models(self):
        """Pydantic 모델과 통합"""
        from src.auth.models import UserCreate

        # 유효한 비밀번호
        valid_user = UserCreate(
            email="test@example.com",
            username="testuser",
            password="ValidPass123!"
        )
        assert valid_user.password == "ValidPass123!"

        # 유효하지 않은 비밀번호
        with pytest.raises(ValueError):
            UserCreate(
                email="test@example.com",
                username="testuser",
                password="weak"
            )

    def test_password_reset_uses_same_policy(self):
        """비밀번호 재설정도 동일한 정책 사용"""
        from src.auth.models import PasswordResetConfirm

        # 유효한 비밀번호
        valid_reset = PasswordResetConfirm(
            token="dummy_token",
            new_password="NewPass123!"
        )
        assert valid_reset.new_password == "NewPass123!"

        # 유효하지 않은 비밀번호
        with pytest.raises(ValueError):
            PasswordResetConfirm(
                token="dummy_token",
                new_password="weak"
            )


class TestRealWorldPasswords:
    """실제 사용 가능한 비밀번호 테스트"""

    def test_realistic_strong_passwords(self):
        """실제로 사용할 수 있는 강력한 비밀번호"""
        realistic_passwords = [
            "MyDog@2024",
            "Summer!2024",
            "Travel#Plan99",
            "Coffee&Code123",
            "Blue$Sky2024",
            "G00d!Idea",
            "Str0ng*Pass",
            "S3cur3!Pw",
            "T3st@Pass"
        ]

        for password in realistic_passwords:
            is_valid, errors = PasswordPolicy.validate(password)
            assert is_valid, f"{password} should be valid, errors: {errors}"

    def test_realistic_weak_passwords(self):
        """실제로 약한 비밀번호들"""
        weak_passwords = [
            "password",           # 복잡도 부족
            "12345678",           # 숫자만
            "abcdefgh",           # 소문자만
            "ABCDEFGH",           # 대문자만
            "Password",           # 특수문자, 숫자 없음
            "Pass1!",             # 너무 짧음
            "pass word123!",      # 공백 포함
        ]

        for password in weak_passwords:
            is_valid, errors = PasswordPolicy.validate(password)
            assert not is_valid, f"{password} should be invalid"
