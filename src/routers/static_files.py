"""
Static Files Router

Serves HTML files with appropriate no-cache headers
to ensure users always get the latest version.
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Static"])

# Get static path from parent directory
static_path = Path(__file__).parent.parent.parent / "static"


@router.get("/", response_class=HTMLResponse)
async def root():
    """Serve main page with no-cache headers"""
    index_file = static_path / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html not found")

    content = index_file.read_text(encoding="utf-8")

    # Always use no-cache for index.html to ensure users get latest version
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.get("/{filename}.html", response_class=HTMLResponse)
async def serve_html(filename: str):
    """Serve HTML files with no-cache headers"""
    # Security: Only allow safe filenames (no path traversal)
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=404, detail="Invalid filename")

    html_file = static_path / f"{filename}.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail=f"{filename}.html not found")

    content = html_file.read_text(encoding="utf-8")

    # No-cache for HTML files to ensure users get latest version
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
