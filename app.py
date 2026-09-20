"""VinUni Compass — application entry point.

    python app.py            # http://127.0.0.1:8000
    python app.py --reload   # restart on source changes

The HTTP layer lives in ``src/vinuni_compass/webapp.py`` and is served by
uvicorn, which is already part of the project's dependencies.
"""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv


load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the VinUni Compass web client.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--reload", action="store_true", help="Restart on source changes.")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "src.vinuni_compass.webapp:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
