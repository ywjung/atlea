"""
IP Address Utilities
Safe handling of client IP addresses from headers and requests
"""
import ipaddress
import re
from typing import Optional, List
from starlette.requests import Request
from loguru import logger


class IPValidator:
    """
    Validates and extracts real client IP addresses
    Prevents IP spoofing through X-Forwarded-For header manipulation
    """

    # Trusted proxy IP ranges (configure for your infrastructure)
    TRUSTED_PROXIES = [
        ipaddress.ip_network('127.0.0.0/8'),      # Localhost
        ipaddress.ip_network('10.0.0.0/8'),       # Private network
        ipaddress.ip_network('172.16.0.0/12'),    # Private network
        ipaddress.ip_network('192.168.0.0/16'),   # Private network
        # Add your load balancer/proxy IPs here
        # ipaddress.ip_network('1.2.3.4/32'),     # Example: specific proxy IP
    ]

    @classmethod
    def is_valid_ip(cls, ip_str: str) -> bool:
        """
        Check if string is a valid IP address

        Args:
            ip_str: IP address string to validate

        Returns:
            True if valid IP, False otherwise
        """
        try:
            ipaddress.ip_address(ip_str)
            return True
        except ValueError:
            return False

    @classmethod
    def is_trusted_proxy(cls, ip_str: str) -> bool:
        """
        Check if IP is a trusted proxy

        Args:
            ip_str: IP address to check

        Returns:
            True if IP is in trusted proxy list
        """
        try:
            ip = ipaddress.ip_address(ip_str)
            return any(ip in network for network in cls.TRUSTED_PROXIES)
        except ValueError:
            return False

    @classmethod
    def sanitize_ip(cls, ip_str: str) -> Optional[str]:
        """
        Sanitize and validate IP address string

        Args:
            ip_str: IP address string (may include port)

        Returns:
            Sanitized IP address or None if invalid
        """
        if not ip_str:
            return None

        # Remove whitespace
        ip_str = ip_str.strip()

        # Remove port if present (format: ip:port)
        if ':' in ip_str and not '[' in ip_str:  # IPv4 with port
            ip_str = ip_str.split(':')[0]
        elif ']:' in ip_str:  # IPv6 with port [::1]:8080
            ip_str = ip_str.split(']:')[0].replace('[', '')

        # Validate IP format
        if not cls.is_valid_ip(ip_str):
            return None

        return ip_str

    @classmethod
    def extract_forwarded_ips(cls, forwarded_for: str) -> List[str]:
        """
        Extract and validate IPs from X-Forwarded-For header

        Args:
            forwarded_for: X-Forwarded-For header value

        Returns:
            List of valid IP addresses (from leftmost to rightmost)
        """
        if not forwarded_for:
            return []

        # Split by comma and sanitize each IP
        ips = []
        for ip_str in forwarded_for.split(','):
            sanitized = cls.sanitize_ip(ip_str)
            if sanitized:
                ips.append(sanitized)

        return ips

    @classmethod
    def get_client_ip(cls, request: Request, trust_proxy: bool = True) -> str:
        """
        Get real client IP address with protection against spoofing

        Args:
            request: Starlette/FastAPI request object
            trust_proxy: If True, trusts X-Forwarded-For from trusted proxies

        Returns:
            Client IP address (validated and sanitized)

        Security Notes:
            - If trust_proxy=False, always returns direct connection IP
            - If trust_proxy=True, validates X-Forwarded-For against trusted proxies
            - Returns leftmost untrusted IP from X-Forwarded-For chain
            - Falls back to direct connection IP if validation fails
        """
        # Get direct connection IP (always available and trustworthy)
        direct_ip = request.client.host if request.client else "unknown"

        # If not trusting proxies, return direct IP
        if not trust_proxy:
            return direct_ip

        # Get X-Forwarded-For header
        forwarded_for = request.headers.get("X-Forwarded-For")
        if not forwarded_for:
            return direct_ip

        # Extract and validate IPs from header
        forwarded_ips = cls.extract_forwarded_ips(forwarded_for)
        if not forwarded_ips:
            logger.warning(f"Invalid X-Forwarded-For header: {forwarded_for}")
            return direct_ip

        # Verify the direct connection IP is a trusted proxy
        if not cls.is_trusted_proxy(direct_ip):
            logger.warning(
                f"Received X-Forwarded-For from untrusted source: {direct_ip}. "
                f"Ignoring header for security."
            )
            return direct_ip

        # Find the leftmost IP that is NOT a trusted proxy
        # This is the real client IP (or the first untrusted proxy)
        for ip in forwarded_ips:
            if not cls.is_trusted_proxy(ip):
                logger.debug(f"Client IP from X-Forwarded-For: {ip}")
                return ip

        # All IPs in chain are trusted proxies, use the leftmost one
        # This can happen in multi-proxy setups
        client_ip = forwarded_ips[0] if forwarded_ips else direct_ip
        logger.debug(f"All proxies trusted, using leftmost: {client_ip}")
        return client_ip

    @classmethod
    def get_all_ips(cls, request: Request) -> dict:
        """
        Get comprehensive IP information for debugging/logging

        Args:
            request: Starlette/FastAPI request object

        Returns:
            Dictionary with all IP information
        """
        direct_ip = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("X-Forwarded-For")
        real_ip = request.headers.get("X-Real-IP")
        client_ip = cls.get_client_ip(request, trust_proxy=True)

        return {
            "client_ip": client_ip,              # Validated real client IP
            "direct_ip": direct_ip,              # Direct connection IP
            "x_forwarded_for": forwarded_for,    # Raw header value
            "x_real_ip": real_ip,                # X-Real-IP header (if present)
            "is_proxied": forwarded_for is not None,
            "is_trusted": cls.is_trusted_proxy(direct_ip)
        }
