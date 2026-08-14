"""Run the FastAPI service with ``python -m app.api``."""

import uvicorn

from app.api.main import app
from app.config import settings


def main() -> None:
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
