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
from datetime import datetime, timedelta
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
        cache_mgr: CacheManager instance (kept for backward compatibility)
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

        # Log security event via SecurityLogger (stores to PostgreSQL)
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
    Get CSP violation statistics from PostgreSQL

    Returns aggregated statistics about CSP violations for monitoring.

    Returns:
        JSON with violation counts by directive and recent violations
    """
    try:
        from ..database.connection import SyncSessionFactory
        from ..database.models.security_log import SecurityLog
        from sqlalchemy import func

        with SyncSessionFactory() as session:
            # Only look at last 24 hours
            since = datetime.utcnow() - timedelta(hours=24)

            # Count by directive (from details JSONB)
            rows = (
                session.query(
                    SecurityLog.details["violated_directive"].as_string().label("directive"),
                    func.count().label("cnt"),
                )
                .filter(
                    SecurityLog.event_type == "CSP_VIOLATION",
                    SecurityLog.created_at >= since,
                )
                .group_by(SecurityLog.details["violated_directive"].as_string())
                .all()
            )

            by_directive = {}
            total = 0
            for row in rows:
                directive = row.directive or "unknown"
                by_directive[directive] = row.cnt
                total += row.cnt

            # Recent 10 violations
            recent_logs = (
                session.query(SecurityLog)
                .filter(
                    SecurityLog.event_type == "CSP_VIOLATION",
                    SecurityLog.created_at >= since,
                )
                .order_by(SecurityLog.created_at.desc())
                .limit(10)
                .all()
            )

            recent_violations = []
            for log in recent_logs:
                violation = {
                    "timestamp": log.created_at.isoformat() if log.created_at else "",
                    "blocked_uri": (log.details or {}).get("blocked_uri", "unknown"),
                    "violated_directive": (log.details or {}).get("violated_directive", "unknown"),
                    "document_uri": (log.details or {}).get("document_uri", "unknown"),
                    "source_file": (log.details or {}).get("source_file", ""),
                    "line_number": (log.details or {}).get("line_number", 0),
                    "client_ip": log.ip_address or "unknown",
                }
                recent_violations.append(violation)

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
    Get recent CSP violations from PostgreSQL

    Args:
        limit: Maximum number of violations to return (default: 50, max: 200)

    Returns:
        List of recent CSP violation records
    """
    try:
        # Validate limit
        limit = min(max(1, limit), 200)

        from ..database.connection import SyncSessionFactory
        from ..database.models.security_log import SecurityLog

        with SyncSessionFactory() as session:
            recent_logs = (
                session.query(SecurityLog)
                .filter(SecurityLog.event_type == "CSP_VIOLATION")
                .order_by(SecurityLog.created_at.desc())
                .limit(limit)
                .all()
            )

            violations = []
            for log in recent_logs:
                violation = {
                    "timestamp": log.created_at.isoformat() if log.created_at else "",
                    "blocked_uri": (log.details or {}).get("blocked_uri", "unknown"),
                    "violated_directive": (log.details or {}).get("violated_directive", "unknown"),
                    "document_uri": (log.details or {}).get("document_uri", "unknown"),
                    "source_file": (log.details or {}).get("source_file", ""),
                    "line_number": (log.details or {}).get("line_number", 0),
                    "client_ip": log.ip_address or "unknown",
                }
                violations.append(violation)

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
