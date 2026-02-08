import asyncio
import base64
from typing import Callable, Awaitable

import aiohttp
import orjson

from .types import TonConnectErrorCode, TonConnectException


def retry(max_attempts: int, backoff: Callable[[int], float]):
    def decorator(func: Callable[..., Awaitable]):
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_error = exc
                    if attempt >= max_attempts:
                        break
                    await asyncio.sleep(backoff(attempt))
            raise last_error

        return wrapper

    return decorator


def exponential(attempt: int, base: float = 0.5) -> float:
    return base * (2 ** (attempt - 1))


class BridgeClient:
    def __init__(
        self,
        bridge_url: str,
        http_session: aiohttp.ClientSession,
    ):
        self.bridge_url = bridge_url
        self.http_session = http_session

    @staticmethod
    def encrypt_message(message: dict, connection_box) -> str:
        encrypted = connection_box.encrypt(orjson.dumps(message))
        return base64.b64encode(encrypted).decode()

    @retry(max_attempts=3, backoff=exponential)
    async def send_to_bridge(self, client_id: str, to_id: str, payload: str):
        async with self.http_session.post(
            f"{self.bridge_url}/message?client_id={client_id}&to={to_id}&ttl=300",
            data=payload,
            headers={"Content-Type": "text/plain"},
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise TonConnectException(
                    TonConnectErrorCode.BRIDGE_ERROR, f"Bridge error: {text}"
                )
