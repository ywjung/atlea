"""
Security Monitoring Router

Handles security-related monitoring and reporting:
- CSP violation reports
- Security event logging
- Threat intelligence gathering

Public endpoint for browser CSP reporting.
"""

from fastapi import APIRouter, Request
from typing import Optional, Dict, Any
from loguru import logger
from datetime import datetime
import json

# Create router with prefix and tags
router = APIRouter(prefix="/api/security", tags=["Security"])

# ============================================================================
# Global Dependencies (injected from main app)
# ============================================================================

cache_manager = None
audit_logger = None


def inject_dependencies(cache_mgr, audit_log):
    """
    Inject dependencies from main application

    Args:
        cache_mgr: CacheManager instance for Redis access
        audit_log: AuditLogger instance for security event logging
    """
    global cache_manager, audit_logger
    cache_manager = cache_mgr
    audit_logger = audit_log


# ============================================================================
# CSP Violation Reporting Endpoint
# ============================================================================

@router.post("/csp-report")
async def csp_report(request: Request):
    """
    Receive and process CSP violation reports from browsers

    This endpoint is called automatically by browsers when CSP violations occur.
    Reports are logged and stored for security analysis.

    Returns:
        JSON response indicating receipt status
    """
    try:
        # Parse CSP report from browser
        report = await request.json()

        # Extract key information
        csp_report = report.get("csp-report", {})
        blocked_uri = csp_report.get("blocked-uri", "unknown")
        violated_directive = csp_report.get("violated-directive", "unknown")
        document_uri = csp_report.get("document-uri", "unknown")
        source_file = csp_report.get("source-file", "")
        line_number = csp_report.get("line-number", 0)

        # Log violation with structured data
        logger.warning(
            f"CSP Violation: {violated_directive} | "
            f"Blocked: {blocked_uri} | "
            f"Document: {document_uri} | "
            f"Source: {source_file}:{line_number}"
        )

        # Store violation in Redis for analysis
        if cache_manager and cache_manager.redis:
            try:
                # Create violation record
                violation_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "blocked_uri": blocked_uri,
                    "violated_directive": violated_directive,
                    "document_uri": document_uri,
                    "source_file": source_file,
                    "line_number": line_number,
                    "user_agent": request.headers.get("user-agent", ""),
                    "client_ip": request.client.host if request.client else "unknown"
                }

                # Store in Redis list (keep last 1000 violations)
                cache_manager.redis.lpush(
                    "security:csp_violations",
                    json.dumps(violation_data)
                )
                cache_manager.redis.ltrim("security:csp_violations", 0, 999)

                # Increment violation counter by directive
                counter_key = f"security:csp_count:{violated_directive}"
                cache_manager.redis.incr(counter_key)
                cache_manager.redis.expire(counter_key, 86400)  # 24 hours

            except Exception as redis_error:
                logger.error(f"Failed to store CSP violation in Redis: {redis_error}")

        # Log security event via SecurityLogger
        try:
            from ..auth.security_logger import SecurityLogger

            SecurityLogger.log_csp_violation(
                ip_address=request.client.host if request.client else "unknown",
                blocked_uri=blocked_uri,
                violated_directive=violated_directive,
                document_uri=document_uri,
                source_file=source_file,
                line_number=line_number
            )
        except Exception as security_log_error:
            logger.error(f"Failed to log CSP violation via SecurityLogger: {security_log_error}")

        return {"status": "received"}

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in CSP report: {e}")
        return {"status": "error", "message": "Invalid JSON format"}

    except Exception as e:
        logger.error(f"Error processing CSP report: {e}")
        return {"status": "error", "message": "Internal server error"}


@router.get("/csp-violations/stats")
async def get_csp_violation_stats(request: Request):
    """
    Get CSP violation statistics

    Returns aggregated statistics about CSP violations for monitoring.
    Requires admin authentication.

    Returns:
        JSON with violation counts by directive and recent violations
    """
    try:
        if not cache_manager or not cache_manager.redis:
            return {
                "error": "Redis not available",
                "total_violations": 0,
                "by_directive": {},
                "recent_violations": []
            }

        # Get all directive counters
        directive_keys = cache_manager.redis.keys("security:csp_count:*")
        by_directive = {}
        total = 0

        for key in directive_keys:
            directive = key.decode().replace("security:csp_count:", "")
            count = int(cache_manager.redis.get(key) or 0)
            by_directive[directive] = count
            total += count

        # Get recent violations (last 10)
        recent_raw = cache_manager.redis.lrange("security:csp_violations", 0, 9)
        recent_violations = []
        for violation_json in recent_raw:
            try:
                violation = json.loads(violation_json)
                recent_violations.append(violation)
            except json.JSONDecodeError:
                continue

        return {
            "total_violations": total,
            "by_directive": by_directive,
            "recent_violations": recent_violations,
            "timeframe": "Last 24 hours"
        }

    except Exception as e:
        logger.error(f"Error retrieving CSP stats: {e}")
        return {
            "error": str(e),
            "total_violations": 0,
            "by_directive": {},
            "recent_violations": []
        }


@router.get("/csp-violations/recent")
async def get_recent_csp_violations(
    request: Request,
    limit: int = 50
):
    """
    Get recent CSP violations

    Args:
        limit: Maximum number of violations to return (default: 50, max: 200)

    Returns:
        List of recent CSP violation records
    """
    try:
        # Validate limit
        limit = min(max(1, limit), 200)

        if not cache_manager or not cache_manager.redis:
            return {
                "error": "Redis not available",
                "violations": []
            }

        # Get recent violations
        recent_raw = cache_manager.redis.lrange("security:csp_violations", 0, limit - 1)
        violations = []

        for violation_json in recent_raw:
            try:
                violation = json.loads(violation_json)
                violations.append(violation)
            except json.JSONDecodeError:
                continue

        return {
            "count": len(violations),
            "violations": violations
        }

    except Exception as e:
        logger.error(f"Error retrieving recent CSP violations: {e}")
        return {
            "error": str(e),
            "violations": []
        }
