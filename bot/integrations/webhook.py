from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiohttp

from config import get_settings

logger = logging.getLogger("surveybot.webhook")


async def _send(event_type: str, data: dict[str, Any]) -> None:
    settings = get_settings()
    if not settings.WEBHOOK_ENABLED or not settings.WEBHOOK_URL:
        return

    payload = {
        "event_type": event_type,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "data": data,
    }
    payload_raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    signature = hmac.new(
        settings.WEBHOOK_SECRET.encode("utf-8"),
        payload_raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-SurveyBot-Signature": signature,
    }

    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(settings.WEBHOOK_URL, data=payload_raw.encode("utf-8"), headers=headers) as resp:
                if 200 <= resp.status < 300:
                    logger.info("Webhook sent successfully: %s", event_type)
                else:
                    body = await resp.text()
                    logger.error("Webhook failed [%s]: %s", resp.status, body[:500])
    except Exception as error:
        logger.exception("Webhook send error (%s): %s", event_type, error)


def send_webhook(event_type: str, data: dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_send(event_type=event_type, data=data))
