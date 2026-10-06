"""Config-driven ASGI startup: python -m app.mcp."""
import uvicorn
from app.core.config import get_settings


def main():
    settings = get_settings()
    uvicorn.run('app.mcp.server:app', host=settings.mcp_host, port=settings.mcp_port,
        proxy_headers=False, access_log=False)


if __name__ == '__main__':
    main()
