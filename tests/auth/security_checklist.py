#!/usr/bin/env python3
"""
Security Checklist Automation Script

자동화된 보안 체크를 수행하고 결과를 리포트합니다.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Dict


class SecurityCheck:
    """보안 체크 결과"""
    def __init__(self, name: str, passed: bool, message: str, severity: str = "info"):
        self.name = name
        self.passed = passed
        self.message = message
        self.severity = severity  # critical, high, medium, low, info


class SecurityChecker:
    """보안 체크리스트 자동화"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results: List[SecurityCheck] = []

    def run_all_checks(self):
        """모든 보안 체크 실행"""
        print("🔒 인증 시스템 보안 체크 시작...\n")

        self.check_env_files()
        self.check_gitignore()
        self.check_password_policy()
        self.check_jwt_config()
        self.check_debug_logging()
        self.check_dependencies()
        self.check_test_coverage()

        self.print_report()

    def check_env_files(self):
        """환경 변수 파일 보안 체크"""
        print("📋 환경 변수 파일 체크...")

        # .env 파일 존재 확인
        env_file = self.project_root / ".env"
        if env_file.exists():
            self.results.append(SecurityCheck(
                "ENV_FILE_EXISTS",
                True,
                "✅ .env 파일이 존재합니다.",
                "info"
            ))

            # JWT_SECRET_KEY 확인
            with open(env_file, 'r') as f:
                content = f.read()
                if 'JWT_SECRET_KEY' in content:
                    # 키 길이 확인
                    match = re.search(r'JWT_SECRET_KEY\s*=\s*["\']?([^"\'\n]+)', content)
                    if match:
                        key = match.group(1)
                        if len(key) >= 32:
                            self.results.append(SecurityCheck(
                                "JWT_SECRET_STRONG",
                                True,
                                f"✅ JWT_SECRET_KEY 길이 충분: {len(key)} 문자",
                                "info"
                            ))
                        else:
                            self.results.append(SecurityCheck(
                                "JWT_SECRET_WEAK",
                                False,
                                f"⚠️ JWT_SECRET_KEY가 너무 짧습니다: {len(key)} 문자 (권장: 32자 이상)",
                                "high"
                            ))
                else:
                    self.results.append(SecurityCheck(
                        "JWT_SECRET_MISSING",
                        False,
                        "❌ JWT_SECRET_KEY가 .env 파일에 없습니다.",
                        "critical"
                    ))
        else:
            self.results.append(SecurityCheck(
                "ENV_FILE_MISSING",
                False,
                "⚠️ .env 파일이 없습니다. .env.example을 복사하여 생성하세요.",
                "medium"
            ))

    def check_gitignore(self):
        """gitignore 파일 체크"""
        print("📋 .gitignore 체크...")

        gitignore_file = self.project_root / ".gitignore"
        if gitignore_file.exists():
            with open(gitignore_file, 'r') as f:
                content = f.read()
                if '.env' in content:
                    self.results.append(SecurityCheck(
                        "GITIGNORE_ENV",
                        True,
                        "✅ .env 파일이 .gitignore에 포함되어 있습니다.",
                        "info"
                    ))
                else:
                    self.results.append(SecurityCheck(
                        "GITIGNORE_ENV_MISSING",
                        False,
                        "❌ .env 파일이 .gitignore에 없습니다. 추가해야 합니다!",
                        "critical"
                    ))
        else:
            self.results.append(SecurityCheck(
                "GITIGNORE_MISSING",
                False,
                "⚠️ .gitignore 파일이 없습니다.",
                "medium"
            ))

    def check_password_policy(self):
        """비밀번호 정책 체크"""
        print("📋 비밀번호 정책 체크...")

        models_file = self.project_root / "src" / "auth" / "models.py"
        if models_file.exists():
            with open(models_file, 'r') as f:
                content = f.read()

                # 최소 길이 확인
                if 'min_length=8' in content or 'min_length=10' in content:
                    self.results.append(SecurityCheck(
                        "PASSWORD_MIN_LENGTH",
                        True,
                        "✅ 비밀번호 최소 길이 정책이 있습니다.",
                        "info"
                    ))
                else:
                    self.results.append(SecurityCheck(
                        "PASSWORD_MIN_LENGTH_MISSING",
                        False,
                        "⚠️ 비밀번호 최소 길이 정책이 없습니다.",
                        "high"
                    ))

                # 복잡도 정책 확인 (권장사항)
                if 'regex' in content or 'pattern' in content:
                    self.results.append(SecurityCheck(
                        "PASSWORD_COMPLEXITY",
                        True,
                        "✅ 비밀번호 복잡도 정책이 구현되어 있습니다.",
                        "info"
                    ))
                else:
                    self.results.append(SecurityCheck(
                        "PASSWORD_COMPLEXITY_RECOMMENDED",
                        False,
                        "💡 권장: 비밀번호 복잡도 정책 추가 (대소문자, 숫자, 특수문자)",
                        "low"
                    ))

    def check_jwt_config(self):
        """JWT 설정 체크"""
        print("📋 JWT 설정 체크...")

        utils_file = self.project_root / "src" / "auth" / "utils.py"
        if utils_file.exists():
            with open(utils_file, 'r') as f:
                content = f.read()

                # HS256 알고리즘 확인
                if 'HS256' in content:
                    self.results.append(SecurityCheck(
                        "JWT_ALGORITHM",
                        True,
                        "✅ JWT 알고리즘: HS256 사용 중",
                        "info"
                    ))

                # 만료 시간 확인
                if 'ACCESS_TOKEN_EXPIRE_MINUTES' in content:
                    match = re.search(r'ACCESS_TOKEN_EXPIRE_MINUTES\s*=\s*(\d+)', content)
                    if match:
                        minutes = int(match.group(1))
                        if 5 <= minutes <= 60:
                            self.results.append(SecurityCheck(
                                "JWT_EXPIRY_GOOD",
                                True,
                                f"✅ Access Token 만료 시간: {minutes}분 (적절)",
                                "info"
                            ))
                        else:
                            self.results.append(SecurityCheck(
                                "JWT_EXPIRY_WARNING",
                                False,
                                f"⚠️ Access Token 만료 시간: {minutes}분 (권장: 5-60분)",
                                "medium"
                            ))

    def check_debug_logging(self):
        """디버그 로깅 체크"""
        print("📋 디버그 로깅 체크...")

        debug_found = []
        for file in self.project_root.glob("src/**/*.py"):
            with open(file, 'r') as f:
                content = f.read()
                if 'logger.debug' in content:
                    debug_found.append(str(file.relative_to(self.project_root)))

        if debug_found:
            self.results.append(SecurityCheck(
                "DEBUG_LOGGING_FOUND",
                False,
                f"⚠️ 디버그 로깅 발견: {', '.join(debug_found[:3])}... "
                f"프로덕션에서 비활성화하세요.",
                "medium"
            ))
        else:
            self.results.append(SecurityCheck(
                "DEBUG_LOGGING_CLEAN",
                True,
                "✅ 디버그 로깅이 없습니다.",
                "info"
            ))

    def check_dependencies(self):
        """의존성 체크"""
        print("📋 의존성 체크...")

        requirements_file = self.project_root / "requirements.txt"
        if requirements_file.exists():
            self.results.append(SecurityCheck(
                "REQUIREMENTS_EXISTS",
                True,
                "✅ requirements.txt 존재",
                "info"
            ))

            with open(requirements_file, 'r') as f:
                content = f.read()

                # 주요 보안 패키지 확인
                if 'passlib' in content and 'bcrypt' in content:
                    self.results.append(SecurityCheck(
                        "CRYPTO_LIBRARY",
                        True,
                        "✅ 암호화 라이브러리: passlib[bcrypt] 사용",
                        "info"
                    ))

                if 'python-jose' in content:
                    self.results.append(SecurityCheck(
                        "JWT_LIBRARY",
                        True,
                        "✅ JWT 라이브러리: python-jose 사용",
                        "info"
                    ))

            # pip-audit 권장
            self.results.append(SecurityCheck(
                "AUDIT_RECOMMENDED",
                False,
                "💡 권장: 정기적으로 'pip-audit' 실행하여 취약점 스캔",
                "low"
            ))

    def check_test_coverage(self):
        """테스트 커버리지 체크"""
        print("📋 테스트 커버리지 체크...")

        test_files = list((self.project_root / "tests" / "auth").glob("test_*.py"))
        if test_files:
            self.results.append(SecurityCheck(
                "TESTS_EXIST",
                True,
                f"✅ 인증 테스트 파일: {len(test_files)}개 발견",
                "info"
            ))

            # 필수 테스트 파일 확인
            required_tests = ["test_utils.py", "test_service.py", "test_middleware.py", "test_api.py"]
            missing_tests = []
            for test_name in required_tests:
                if not (self.project_root / "tests" / "auth" / test_name).exists():
                    missing_tests.append(test_name)

            if not missing_tests:
                self.results.append(SecurityCheck(
                    "COMPLETE_TEST_SUITE",
                    True,
                    "✅ 모든 필수 테스트 파일 존재",
                    "info"
                ))
            else:
                self.results.append(SecurityCheck(
                    "MISSING_TESTS",
                    False,
                    f"⚠️ 누락된 테스트 파일: {', '.join(missing_tests)}",
                    "medium"
                ))
        else:
            self.results.append(SecurityCheck(
                "NO_TESTS",
                False,
                "❌ 인증 테스트 파일이 없습니다!",
                "critical"
            ))

    def print_report(self):
        """보안 체크 결과 출력"""
        print("\n" + "="*60)
        print("🔒 보안 체크 결과 리포트")
        print("="*60 + "\n")

        # 심각도별 분류
        critical = [r for r in self.results if r.severity == "critical"]
        high = [r for r in self.results if r.severity == "high"]
        medium = [r for r in self.results if r.severity == "medium"]
        low = [r for r in self.results if r.severity == "low"]
        info = [r for r in self.results if r.severity == "info"]

        # Critical 이슈
        if critical:
            print("🔴 CRITICAL 이슈:")
            for result in critical:
                print(f"  - {result.message}")
            print()

        # High 이슈
        if high:
            print("🟠 HIGH 우선순위:")
            for result in high:
                print(f"  - {result.message}")
            print()

        # Medium 이슈
        if medium:
            print("🟡 MEDIUM 우선순위:")
            for result in medium:
                print(f"  - {result.message}")
            print()

        # Low 이슈
        if low:
            print("🟢 LOW 우선순위 (권장사항):")
            for result in low:
                print(f"  - {result.message}")
            print()

        # 정보
        print("ℹ️  통과한 체크:")
        for result in info:
            print(f"  - {result.message}")
        print()

        # 요약
        total = len(self.results)
        passed = len([r for r in self.results if r.passed])
        failed = total - passed

        print("="*60)
        print(f"총 {total}개 체크 | 통과: {passed} | 주의: {failed}")

        if critical:
            print(f"\n⚠️  {len(critical)}개의 CRITICAL 이슈를 즉시 해결하세요!")
            return 1
        elif high:
            print(f"\n⚠️  {len(high)}개의 HIGH 우선순위 이슈를 확인하세요.")
            return 0
        else:
            print("\n✅ 심각한 보안 이슈가 발견되지 않았습니다.")
            return 0


def main():
    """메인 함수"""
    # 프로젝트 루트 찾기
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent

    # 보안 체커 실행
    checker = SecurityChecker(project_root)
    exit_code = checker.run_all_checks()

    print("\n💡 상세한 보안 가이드: tests/auth/SECURITY_REVIEW.md")
    print("="*60)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
