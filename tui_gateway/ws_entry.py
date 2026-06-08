"""Standalone WebSocket server entry point for tui_gateway.

Runs tui_gateway as a persistent s6-supervised service inside the Hermes
Docker container.  BFF (yunyi) connects via ``ws://<container>:<port>/ws``
instead of ``docker exec`` stdio, eliminating per-session process spawn
overhead and keeping sessions alive across BFF reconnections.

Usage (inside container, typically via s6 service):
    python -m tui_gateway.ws_entry

Environment variables:
    HERMES_GATEWAY_WS_PORT   TCP port to listen on (default: 8643).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("tui_gateway.ws_entry")


def main() -> None:
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute

    from tui_gateway.ws import handle_ws

    port = int(os.environ.get("HERMES_GATEWAY_WS_PORT") or "8643")

    app = Starlette(
        routes=[
            WebSocketRoute("/ws", handle_ws),
        ],
    )

    logger.info("tui_gateway WebSocket server starting on :%d", port)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        ws_ping_interval=30,
        ws_ping_timeout=60,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s: %(message)s",
    )
    main()
