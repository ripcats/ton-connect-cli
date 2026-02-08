import asyncio
import os
import time
from typing import Optional

import aiohttp
from dotenv import load_dotenv

from .bridge_client import BridgeClient
from .ton_wallet import HeadlessTonConnectWallet, validate_mnemonic
from .types import (
    TonConnectErrorCode,
    TonConnectException,
    TonConnectResult,
    TonConnectResultCode,
)
from .url_parser import (
    extract_domain,
    get_tc_domain,
    parse_tc_url,
    sanitize_allowed_domains,
    validate_tc_url,
)

load_dotenv()


class TonConnectClient:
    def __init__(
        self,
        mnemonic: Optional[str] = None,
        bridge_url: str = None,
        connect_timeout: Optional[float] = 10,
        request_timeout: Optional[float] = 30,
    ):
        self.mnemonic = mnemonic or os.getenv("TON_WALLET_MNEMONIC", "")
        self.bridge_url = bridge_url or "https://bridge.tonapi.io/bridge"
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self._wallet: Optional[HeadlessTonConnectWallet] = None
        self._allowed_domains: Optional[set[str]] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._bridge_client: Optional[BridgeClient] = None

    async def init(self, allowed_domains: Optional[list[str]] = None):
        self._allowed_domains = sanitize_allowed_domains(allowed_domains)
        await self.init_wallet()

    async def init_wallet(self):
        if not self.mnemonic.strip():
            raise TonConnectException(
                TonConnectErrorCode.MNEMONIC_NOT_SPECIFIED,
                "TON_WALLET_MNEMONIC is not specified",
            )
        if self._wallet is None:
            mnemonics = validate_mnemonic(self.mnemonic)
            self._wallet = HeadlessTonConnectWallet(
                seed_phrase=mnemonics, bridge_url=self.bridge_url
            )
        try:
            await self._wallet.init_wallet(timeout=self.connect_timeout)
        except Exception as e:
            raise TonConnectException(
                TonConnectErrorCode.WALLET_INIT_FAILED, str(e)
            ) from e
        finally:
            self.mnemonic = ""
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(
                    total=self.request_timeout, connect=self.connect_timeout
                )
            )
        if self._bridge_client is None:
            self._bridge_client = BridgeClient(
                bridge_url=self.bridge_url, http_session=self._http_session
            )

    async def connect(self, tc_url: str) -> TonConnectResult:
        if not validate_tc_url(tc_url):
            raise TonConnectException(
                TonConnectErrorCode.INVALID_TC_URL, "Invalid tc:// URL"
            )
        if self._allowed_domains:
            domain = get_tc_domain(tc_url)
            if not domain or domain.lower() not in self._allowed_domains:
                return TonConnectResult(
                    code=TonConnectResultCode.FORBIDDEN,
                    error_code=TonConnectErrorCode.FORBIDDEN,
                    error_message="Domain is not allowed",
                )
        if self._wallet is None:
            await self.init_wallet()
        try:
            started_ms = time.monotonic()
            parsed = parse_tc_url(tc_url)
            request = parsed.get("request", {})
            if "items" not in request or len(request["items"]) == 0:
                raise TonConnectException(
                    TonConnectErrorCode.CONNECT_FAILED, "No connection request items"
                )
            manifest_url = request.get("manifestUrl", "")
            app_domain = extract_domain(manifest_url)
            if manifest_url and self._http_session:
                try:
                    async with self._http_session.get(manifest_url) as resp:
                        if resp.status == 200:
                            manifest = await resp.json()
                            app_url = manifest.get("url", "")
                            if app_url:
                                app_domain = extract_domain(app_url)
                except Exception:
                    pass
            self._wallet.prepare_connection(parsed["id"])
            wallet_info = self._wallet.build_wallet_info()
            proof_item = self._wallet.build_proof_item(
                request=request, app_domain=app_domain, timestamp=int(time.time())
            )
            connect_event = {
                "event": "connect",
                "id": int(time.time() * 1000),
                "payload": {
                    "items": [wallet_info] + ([proof_item] if proof_item else []),
                    "device": {
                        "platform": "android",
                        "appName": "Tonkeeper",
                        "appVersion": "5.4.43",
                        "maxProtocolVersion": 2,
                        "features": [],
                    },
                },
            }
            if not self._wallet.connection_box or not self._bridge_client:
                raise TonConnectException(
                    TonConnectErrorCode.WALLET_INIT_FAILED,
                    "Connection not initialized",
                )
            encrypted_response = self._bridge_client.encrypt_message(
                connect_event, self._wallet.connection_box
            )
            await self._bridge_client.send_to_bridge(
                client_id=self._wallet.client_id,
                to_id=parsed["id"],
                payload=encrypted_response,
            )
            data = connect_event
            elapsed_ms = int((time.monotonic() - started_ms) * 1000)
            if isinstance(data, dict):
                data = {
                    "id": data.get("id"),
                    "event": data.get("event"),
                    "elapsed_ms": elapsed_ms,
                }
            return TonConnectResult(
                code=TonConnectResultCode.DAPP_CONNECTED,
                data=data,
            )
        except TonConnectException as e:
            return TonConnectResult(
                code=TonConnectResultCode.DAPP_CONNECTED_FAILED,
                error_code=e.code,
                error_message=str(e),
            )
        except Exception as e:
            return TonConnectResult(
                code=TonConnectResultCode.DAPP_CONNECTED_FAILED,
                error_code=TonConnectErrorCode.CONNECT_FAILED,
                error_message=str(e),
            )

    async def close(self):
        try:
            if self._wallet:
                await self._wallet.close(timeout=self.request_timeout)
        except asyncio.TimeoutError:
            pass
        if self._http_session:
            try:
                await asyncio.wait_for(
                    self._http_session.close(), timeout=self.request_timeout
                )
            except asyncio.TimeoutError:
                pass


async def connect_tc_url(
    tc_url: str, mnemonic: Optional[str] = None
) -> TonConnectResult:
    client = TonConnectClient(mnemonic=mnemonic)
    try:
        return await client.connect(tc_url)
    finally:
        await client.close()
