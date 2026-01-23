"""
Security validation utilities for preventing SSRF, XSS, and other attacks
"""
import re
import ipaddress
from urllib.parse import urlparse
from typing import Optional, Tuple, List, Pattern, Set, Final


class SSRFValidator:
    """
    Server-Side Request Forgery (SSRF) protection validator
    Prevents requests to internal/private networks and localhost
    """

    # Private IP ranges (RFC 1918)
    PRIVATE_IP_RANGES: Final[List[ipaddress.IPv4Network | ipaddress.IPv6Network]] = [
        ipaddress.ip_network('10.0.0.0/8'),
        ipaddress.ip_network('172.16.0.0/12'),
        ipaddress.ip_network('192.168.0.0/16'),
        ipaddress.ip_network('127.0.0.0/8'),  # Loopback
        ipaddress.ip_network('169.254.0.0/16'),  # Link-local (AWS metadata)
        ipaddress.ip_network('::1/128'),  # IPv6 loopback
        ipaddress.ip_network('fc00::/7'),  # IPv6 private
        ipaddress.ip_network('fe80::/10'),  # IPv6 link-local
    ]

    # Dangerous schemes
    BLOCKED_SCHEMES: Final[List[str]] = [
        'file', 'gopher', 'dict', 'ftp', 'jar',
        'data', 'tftp', 'ldap', 'telnet'
    ]

    # Blocked hostnames
    BLOCKED_HOSTS: Final[List[str]] = [
        'localhost',
        'metadata.google.internal',  # GCP metadata
        'metadata',
    ]

    @classmethod
    def is_private_ip(cls, ip_str: str) -> bool:
        """Check if IP address is private/internal"""
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in network for network in cls.PRIVATE_IP_RANGES)
        except ValueError:
            return False

    @classmethod
    def validate_url(cls, url: str, allow_private: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Validate URL for SSRF protection

        Args:
            url: URL to validate
            allow_private: If True, allows private IPs (use with caution)

        Returns:
            (is_valid, error_message) tuple
        """
        if not url:
            return False, "URL이 비어있습니다"

        try:
            parsed = urlparse(url)

            # Check scheme
            if not parsed.scheme:
                return False, "URL 스키마가 없습니다"

            if parsed.scheme.lower() in cls.BLOCKED_SCHEMES:
                return False, f"허용되지 않는 URL 스키마입니다: {parsed.scheme}"

            # Only allow http and https
            if parsed.scheme.lower() not in ['http', 'https']:
                return False, "HTTP 또는 HTTPS URL만 허용됩니다"

            # Check hostname
            if not parsed.hostname:
                return False, "호스트명이 없습니다"

            hostname = parsed.hostname.lower()

            # Check blocked hostnames
            if hostname in cls.BLOCKED_HOSTS:
                return False, f"허용되지 않는 호스트입니다: {hostname}"

            # Check for IP address
            try:
                ip = ipaddress.ip_address(hostname)
                if not allow_private and cls.is_private_ip(hostname):
                    return False, "내부 IP 주소는 허용되지 않습니다"
            except ValueError:
                # Not an IP address, it's a hostname - this is fine
                pass

            # Check for localhost variations
            if re.match(r'^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|::1)$', hostname):
                return False, "localhost는 허용되지 않습니다"

            # Check for cloud metadata endpoints
            if hostname.startswith('169.254.'):
                return False, "클라우드 메타데이터 엔드포인트는 허용되지 않습니다"

            # Additional checks for malicious redirects
            if '@' in url:
                return False, "URL에 @ 문자는 허용되지 않습니다"

            return True, None

        except Exception as e:
            return False, f"URL 파싱 오류: {str(e)}"


class InputValidator:
    """
    General input validation utilities
    """

    @staticmethod
    def validate_filename(filename: str) -> Tuple[bool, Optional[str]]:
        """
        Validate filename to prevent path traversal

        Args:
            filename: Filename to validate

        Returns:
            (is_valid, error_message) tuple
        """
        if not filename:
            return False, "파일명이 비어있습니다"

        # Check for path traversal patterns
        dangerous_patterns = ['..', '/', '\\', '\x00']
        for pattern in dangerous_patterns:
            if pattern in filename:
                return False, f"파일명에 허용되지 않는 문자가 포함되어 있습니다: {pattern}"

        # Check length
        if len(filename) > 255:
            return False, "파일명이 너무 깁니다 (최대 255자)"

        # Check for valid characters only
        if not re.match(r'^[a-zA-Z0-9._-]+$', filename):
            return False, "파일명에 허용되지 않는 문자가 포함되어 있습니다"

        return True, None

    @staticmethod
    def sanitize_sql_like_pattern(pattern: str) -> str:
        """
        Sanitize SQL LIKE pattern by escaping special characters

        Args:
            pattern: Pattern to sanitize

        Returns:
            Sanitized pattern
        """
        # Escape special SQL LIKE characters
        pattern = pattern.replace('\\', '\\\\')
        pattern = pattern.replace('%', '\\%')
        pattern = pattern.replace('_', '\\_')
        return pattern


class SubprocessValidator:
    """
    Subprocess command validation utilities
    Prevents command injection and validates inputs for subprocess calls
    """

    # Docker 컨테이너 이름 패턴 (알파벳, 숫자, 밑줄, 하이픈, 점만 허용)
    DOCKER_CONTAINER_NAME_PATTERN: Final[Pattern[str]] = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$')

    # 허용된 Docker 명령어 (화이트리스트)
    ALLOWED_DOCKER_COMMANDS: Final[Set[str]] = {
        'ps', 'cp', 'exec', 'inspect'
    }

    # 위험한 쉘 문자
    DANGEROUS_SHELL_CHARS: Final[List[str]] = ['|', '&', ';', '$', '`', '(', ')', '{', '}', '<', '>', '\n', '\r', '\x00']

    @classmethod
    def validate_docker_container_name(cls, name: str) -> Tuple[bool, Optional[str]]:
        """
        Docker 컨테이너 이름 검증

        Args:
            name: 컨테이너 이름

        Returns:
            (is_valid, error_message) tuple
        """
        if not name:
            return False, "컨테이너 이름이 비어있습니다"

        if len(name) > 128:
            return False, "컨테이너 이름이 너무 깁니다 (최대 128자)"

        if not cls.DOCKER_CONTAINER_NAME_PATTERN.match(name):
            return False, "컨테이너 이름에 허용되지 않는 문자가 포함되어 있습니다"

        # 위험한 쉘 문자 검사
        for char in cls.DANGEROUS_SHELL_CHARS:
            if char in name:
                return False, f"컨테이너 이름에 위험한 문자가 포함되어 있습니다: {repr(char)}"

        return True, None

    @classmethod
    def validate_path_for_subprocess(cls, path: str) -> Tuple[bool, Optional[str]]:
        """
        subprocess에서 사용할 경로 검증

        Args:
            path: 파일/디렉토리 경로

        Returns:
            (is_valid, error_message) tuple
        """
        if not path:
            return False, "경로가 비어있습니다"

        if len(path) > 4096:
            return False, "경로가 너무 깁니다"

        # 위험한 쉘 문자 검사
        for char in cls.DANGEROUS_SHELL_CHARS:
            if char in path:
                return False, f"경로에 위험한 문자가 포함되어 있습니다: {repr(char)}"

        # 경로 탐색 패턴 검사 (상대 경로로 상위 디렉토리 접근 시도)
        if '..' in path.split('/'):
            return False, "상위 디렉토리 접근은 허용되지 않습니다"

        return True, None

    @classmethod
    def validate_docker_command(cls, command: str) -> Tuple[bool, Optional[str]]:
        """
        Docker 명령어 검증 (화이트리스트 기반)

        Args:
            command: Docker 하위 명령어 (ps, cp, exec 등)

        Returns:
            (is_valid, error_message) tuple
        """
        if not command:
            return False, "명령어가 비어있습니다"

        if command not in cls.ALLOWED_DOCKER_COMMANDS:
            return False, f"허용되지 않는 Docker 명령어입니다: {command}"

        return True, None

    @classmethod
    def sanitize_for_shell(cls, value: str) -> str:
        """
        쉘 명령어에서 사용할 값 정제 (위험한 문자 제거)

        Args:
            value: 정제할 값

        Returns:
            정제된 값
        """
        if not value:
            return ""

        # 위험한 문자 제거
        for char in cls.DANGEROUS_SHELL_CHARS:
            value = value.replace(char, '')

        return value.strip()
