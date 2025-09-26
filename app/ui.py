"""
UI routes and template rendering for chfs-py
"""

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .models import ApiResponse, ResponseCode
from .auth import get_current_user_optional, UserInfo
from .rules import get_accessible_roots
from .config import get_config
from .ipfilter import get_client_ip

logger = logging.getLogger(__name__)

# UI router
ui_router = APIRouter(tags=["ui"])

# Templates
templates_dir = Path("templates")
if templates_dir.exists():
    templates = Jinja2Templates(directory=str(templates_dir))
else:
    templates = None
    logger.warning("Templates directory not found")


@ui_router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    user: Optional[UserInfo] = Depends(get_current_user_optional)
):
    """Main file browser interface"""
    
    if not templates:
        return HTMLResponse("<h1>Templates not found</h1>", status_code=500)
    
    config = get_config()
    client_ip = get_client_ip(request)
    
    # Get accessible roots for user
    accessible_roots = get_accessible_roots(user, client_ip) if user else []
    
    # Template context
    context = {
        "request": request,
        "config": config,
        "user": user,
        "accessible_roots": accessible_roots,
        "authenticated": user is not None,
        "brand": config.ui.brand,
        "title": config.ui.title,
        "language": config.ui.language,
    }
    
    return templates.TemplateResponse("index.html", context)


@ui_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page (optional)"""
    
    if not templates:
        return HTMLResponse("""
        <html>
        <head><title>Login Required</title></head>
        <body>
            <h1>Authentication Required</h1>
            <p>Please use HTTP Basic Authentication to access this service.</p>
            <p>Your browser should prompt you for credentials.</p>
        </body>
        </html>
        """)
    
    config = get_config()
    
    context = {
        "request": request,
        "config": config,
        "brand": config.ui.brand,
        "title": config.ui.title,
        "language": config.ui.language,
    }
    
    return templates.TemplateResponse("login.html", context)


def setup_ui_routes(app):
    """Setup UI routes"""
    app.include_router(ui_router)
    logger.info("UI routes setup complete")


# Template filters and functions
def setup_template_filters():
    """Setup custom template filters"""
    
    if not templates:
        return
    
    from .utils import format_file_size, format_timestamp
    
    # Add custom filters
    templates.env.filters["filesize"] = format_file_size
    templates.env.filters["timestamp"] = format_timestamp
    
    # Add global functions
    templates.env.globals["enumerate"] = enumerate
    templates.env.globals["len"] = len


# Initialize template filters
setup_template_filters()
