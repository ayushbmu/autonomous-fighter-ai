from __future__ import annotations

import uvicorn

from api.server import app
from common.logging_config import configure_logging
from common.settings import load_runtime_settings


def main() -> None:
    configure_logging()
    settings = load_runtime_settings()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")


if __name__ == "__main__":
    main()
