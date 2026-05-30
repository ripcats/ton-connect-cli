import asyncio
import base64
import json
import os
import time
from typing import Optional

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from nacl.encoding import RawEncoder
from nacl.public import Box, PrivateKey, PublicKey

from .bridge_client import BridgeClient
from .proof_generator import build_ton_proof_item
from .ton_wallet import HeadlessTonConnectWallet, validate_mnemonic
from .types import (
    TonConnectErrorCode,
    TonConnectException,
    TonConnectResult,
    TonConnectResultCode,
    WalletVersion,
)
from .url_parser import (
    extract_domain,
    get_tc_domain,
    is_ton_login_url,
    parse_tc_url,
    parse_ton_login_url,
    sanitize_allowed_domains,
    validate_tc_url,
)

load_dotenv()


class TonConnectClient:
    """
    Headless TonConnect client.

    Supports use as an async context manager for automatic cleanup::

        async with TonConnectClient(mnemonic="...") as client:
            result = await client.connect(tc_url)

    Or manual lifecycle management::

        client = TonConnectClient(mnemonic="...")
        await client.init()
        result = await client.connect(tc_url)
        await client.close()
    """

    def __init__(
        self,
        mnemonic: Optional[str] = None,
        bridge_url: Optional[str] = None,
        wallet_version: Optional[WalletVersion] = None,
        connect_timeout: Optional[float] = 10,
        request_timeout: Optional[float] = 30,
        retry_attempts: int = 3,
        retry_base: float = 0.5,
        allowed_domains: Optional[list[str]] = None,
    ):
        """
        Args:
            mnemonic: 24-word seed phrase. Falls back to TON_WALLET_MNEMONIC env var.
            bridge_url: TonConnect bridge URL. Defaults to bridge.tonapi.io.
            wallet_version: WalletVersion.V5R1 or WalletVersion.V4R2.
                            Falls back to TON_WALLET_VERSION env var, then V5R1.
            connect_timeout: Timeout for wallet initialization (seconds).
            request_timeout: Timeout for HTTP requests (seconds).
            retry_attempts: Number of bridge send retries on failure.
            retry_base: Base delay (seconds) for exponential backoff between retries.
            allowed_domains: Optional whitelist of domains. Connections to domains not
                             in this list will return FORBIDDEN. Can also be set or
                             changed later via the ``allowed_domains`` property or the
                             ``allow_domain`` / ``deny_domain`` helpers.
        """
        self.mnemonic = mnemonic or os.getenv("TON_WALLET_MNEMONIC", "")
        self.bridge_url = bridge_url or "https://bridge.tonapi.io/bridge"
        self.wallet_version = wallet_version
        self.connect_timeout = connect_timeout
        self.request_timeout = request_timeout
        self.retry_attempts = retry_attempts
        self.retry_base = retry_base
        self._wallet: Optional[HeadlessTonConnectWallet] = None
        self._allowed_domains: Optional[set[str]] = sanitize_allowed_domains(allowed_domains)
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._bridge_client: Optional[BridgeClient] = None

    @property
    def allowed_domains(self) -> Optional[set[str]]:
        """Current domain whitelist (``None`` means all domains are allowed)."""
        return self._allowed_domains

    @allowed_domains.setter
    def allowed_domains(self, domains: Optional[list[str]]) -> None:
        """Replace the whitelist entirely.

        Pass ``None`` to disable filtering (allow all domains).

        Example::

            client.allowed_domains = ["app.example.com", "dapp.io"]
            client.allowed_domains = None  # allow everything
        """
        self._allowed_domains = sanitize_allowed_domains(domains)



    async def __aenter__(self) -> "TonConnectClient":
        await self.init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def init(self, allowed_domains: Optional[list[str]] = None) -> None:
        """Initialize the wallet and HTTP session.

        Args:
            allowed_domains: Optional whitelist of domains. Connections to
                             domains not in this list will return FORBIDDEN.
                             If ``allowed_domains`` was already set via the constructor
                             or the property, passing ``None`` here leaves it unchanged.
        """
        if allowed_domains is not None:
            self._allowed_domains = sanitize_allowed_domains(allowed_domains)
        await self._init_wallet()

    async def _init_wallet(self) -> None:
        if not self.mnemonic.strip():
            raise TonConnectException(
                TonConnectErrorCode.MNEMONIC_NOT_SPECIFIED,
                "TON_WALLET_MNEMONIC is not specified",
            )
        if self._wallet is None:
            mnemonics = validate_mnemonic(self.mnemonic)
            self._wallet = HeadlessTonConnectWallet(
                seed_phrase=mnemonics,
                bridge_url=self.bridge_url,
                wallet_version=self.wallet_version,
            )
        try:
            await self._wallet.init_wallet(timeout=self.connect_timeout)
        except TonConnectException:
            raise
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
                bridge_url=self.bridge_url,
                http_session=self._http_session,
                retry_attempts=self.retry_attempts,
                retry_base=self.retry_base,
            )

    async def close(self) -> None:
        """Close all connections and release resources."""
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

    async def connect(self, tc_url: str) -> TonConnectResult:
        """Connect to a dApp via a tc:// or Tonkeeper ton-login URL.

        Args:
            tc_url: TonConnect deep link (``tc://``) **or** a Tonkeeper
                    ton-login deep link
                    (``https://app.tonkeeper.com/ton-login/…``).

        Returns:
            TonConnectResult with code DAPP_CONNECTED, FORBIDDEN, or
            DAPP_CONNECTED_FAILED.

        Raises:
            TonConnectException: If the URL is invalid or wallet is not initialized.
        """
        if is_ton_login_url(tc_url):
            return await self._connect_ton_login(tc_url)

        if not validate_tc_url(tc_url):
            raise TonConnectException(
                TonConnectErrorCode.INVALID_TC_URL, "Invalid tc:// URL"
            )

        if self._allowed_domains:
            domain = get_tc_domain(tc_url)
            if not domain or domain.lower() not in self._allowed_domains:
                logger.warning(f"Domain blocked by whitelist: {domain!r}")
                return TonConnectResult(
                    code=TonConnectResultCode.FORBIDDEN,
                    error_code=TonConnectErrorCode.FORBIDDEN,
                    error_message=f"Domain is not allowed: {domain}",
                )

        if self._wallet is None:
            await self._init_wallet()

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

            logger.debug(f"Connecting to dApp domain: {app_domain!r}")

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
                        "appVersion": "2026.0.0",
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

            elapsed_ms = int((time.monotonic() - started_ms) * 1000)
            logger.info(f"Connected to {app_domain!r} in {elapsed_ms}ms")

            return TonConnectResult(
                code=TonConnectResultCode.DAPP_CONNECTED,
                data={
                    "id": connect_event.get("id"),
                    "event": connect_event.get("event"),
                    "elapsed_ms": elapsed_ms,
                },
            )

        except TonConnectException as e:
            logger.error(f"Connect failed [{e.code}]: {e}")
            return TonConnectResult(
                code=TonConnectResultCode.DAPP_CONNECTED_FAILED,
                error_code=e.code,
                error_message=str(e),
            )
        except Exception as e:
            logger.error(f"Unexpected error during connect: {e}")
            return TonConnectResult(
                code=TonConnectResultCode.DAPP_CONNECTED_FAILED,
                error_code=TonConnectErrorCode.CONNECT_FAILED,
                error_message=str(e),
            )

    async def _connect_ton_login(self, url: str) -> TonConnectResult:
        """Handle Tonkeeper ton-login v1 (ton-auth) deep-links.

        Flow:
          1. Parse the URL to get domain + temp_session
          2. GET authRequest JSON (public endpoint, no auth needed)
          3. Derive wallet keys offline (no TON liteserver)
          4. Sign ton_proof using v1.session as the payload
          5. Encrypt response JSON with NaCl Box(ephemeral_sk, server_session_pk)
          6. POST {id, body} to authResponse callback
        """
        try:
            started_ms = time.monotonic()
            parsed = parse_ton_login_url(url)
            domain = parsed["domain"]
            auth_req_url = parsed["auth_request_url"]

            logger.debug(f"ton-login domain={domain!r} fetching authRequest…")

            if self._http_session is None:
                self._http_session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(
                        total=self.request_timeout, connect=self.connect_timeout
                    )
                )

            if self._allowed_domains and domain.lower() not in self._allowed_domains:
                logger.warning(f"Domain blocked by whitelist: {domain!r}")
                return TonConnectResult(
                    code=TonConnectResultCode.FORBIDDEN,
                    error_code=TonConnectErrorCode.FORBIDDEN,
                    error_message=f"Domain is not allowed: {domain}",
                )

            async with self._http_session.get(auth_req_url) as r:
                auth_req = await r.json(content_type=None)

            v1 = auth_req.get("v1", {})
            session_b64: str = v1["session"]
            callback_url: str = v1["callback_url"]

            if self._wallet is None:
                await self._init_wallet()

            wallet_address = self._wallet.wallet_address
            wallet_private_key = self._wallet.wallet_private_key
            wallet_public_key = self._wallet.wallet_public_key
            wallet_info = self._wallet.build_wallet_info()

            ts = int(time.time())
            proof_item = build_ton_proof_item(
                wallet_address=wallet_address,
                wallet_private_key=wallet_private_key,
                payload=session_b64,
                domain=domain,
                timestamp=ts,
            )
            if not proof_item:
                raise TonConnectException(
                    TonConnectErrorCode.CONNECT_FAILED, "ton_proof signing returned None"
                )

            client_sk = PrivateKey.generate()
            client_pk_b64 = base64.b64encode(bytes(client_sk.public_key)).decode()
            server_pk = PublicKey(base64.b64decode(session_b64), encoder=RawEncoder)
            box = Box(client_sk, server_pk)

            response_payload = {
                "clientId": client_pk_b64,
                "items": [
                    {
                        "type": "ton-ownership",
                        "address": wallet_info["address"],
                        "proof": proof_item["proof"],
                        "publicKey": wallet_public_key,
                        "walletStateInit": wallet_info["walletStateInit"],
                    }
                ],
            }
            encrypted = box.encrypt(json.dumps(response_payload).encode())
            body_b64 = base64.b64encode(bytes(encrypted)).decode()

            async with self._http_session.post(
                callback_url,
                json={"id": client_pk_b64, "body": body_b64},
                headers={"Content-Type": "application/json"},
            ) as r:
                cb_status = r.status
                cb_text = await r.text()

            elapsed_ms = int((time.monotonic() - started_ms) * 1000)
            logger.info(
                f"ton-login {domain!r}: callback HTTP {cb_status} in {elapsed_ms}ms"
            )

            return TonConnectResult(
                code=TonConnectResultCode.DAPP_CONNECTED,
                data={
                    "domain": domain,
                    "callback_status": cb_status,
                    "callback_body": cb_text[:200],
                    "elapsed_ms": elapsed_ms,
                },
            )

        except TonConnectException:
            raise
        except Exception as e:
            logger.error(f"ton-login connect failed: {e}")
            return TonConnectResult(
                code=TonConnectResultCode.DAPP_CONNECTED_FAILED,
                error_code=TonConnectErrorCode.CONNECT_FAILED,
                error_message=str(e),
            )


async def connect_tc_url(
    tc_url: str,
    mnemonic: Optional[str] = None,
    wallet_version: Optional[WalletVersion] = None,
    allowed_domains: Optional[list[str]] = None,
) -> TonConnectResult:
    """One-shot helper: create a client, connect, and close.

    Args:
        tc_url: TonConnect deep link starting with ``tc://``.
        mnemonic: 24-word seed phrase. Falls back to TON_WALLET_MNEMONIC env var.
        wallet_version: WalletVersion.V5R1 or WalletVersion.V4R2.
        allowed_domains: Optional whitelist of domains. Connections to domains not
                         in this list will return FORBIDDEN. Pass ``None`` to allow
                         all domains.
    """
    async with TonConnectClient(
        mnemonic=mnemonic,
        wallet_version=wallet_version,
        allowed_domains=allowed_domains,
    ) as client:
        return await client.connect(tc_url)
