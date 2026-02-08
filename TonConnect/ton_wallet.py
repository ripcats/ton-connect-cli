import asyncio
import base64
import ctypes
import os
from typing import Optional
from nacl.encoding import RawEncoder
from nacl.public import PrivateKey, PublicKey, Box
from pytoniq import LiteBalancer, WalletV5R1, WalletV4R2
from pytoniq_core import Address
from pytoniq_core.crypto.keys import mnemonic_to_private_key

from .proof_generator import build_ton_proof_item
from .types import TonConnectErrorCode, TonConnectException


def validate_mnemonic(mnemonic: str) -> list[str]:
    words = [word.strip().lower() for word in mnemonic.strip().split()]
    if len(words) != 24:
        raise TonConnectException(
            TonConnectErrorCode.MNEMONIC_NOT_SPECIFIED,
            "Mnemonic must contain exactly 24 words",
        )
    if not all(word.isalpha() for word in words):
        raise TonConnectException(
            TonConnectErrorCode.MNEMONIC_NOT_SPECIFIED,
            "Mnemonic contains invalid characters",
        )
    return words


def clear_mnemonic(words: list[str]):
    joined = " ".join(words)
    buffer = bytearray(joined, "utf-8")
    ctypes.memset(ctypes.addressof(ctypes.c_char.from_buffer(buffer)), 0, len(buffer))
    for idx in range(len(words)):
        words[idx] = ""
    words.clear()


class HeadlessTonConnectWallet:
    def __init__(self, seed_phrase: list[str], bridge_url: str):
        self.seed_phrase = seed_phrase
        self.bridge_url = bridge_url
        self.session_private_key = PrivateKey.generate()
        self.session_public_key = self.session_private_key.public_key
        self.client_id = self.session_public_key.encode().hex()
        self.wallet = None
        self.wallet_address = None
        self.wallet_public_key = None
        self.wallet_private_key = None
        self.provider = None
        self.dapp_public_key = None
        self.connection_box = None

    async def init_wallet(self, timeout: Optional[float] = None):
        async def _do_init():
            self.provider = LiteBalancer.from_mainnet_config(1)
            await self.provider.start_up()
            self.wallet, _ = await self._init_wallet()
            self.wallet_address = self.wallet.address.to_str(
                is_bounceable=True, is_user_friendly=True
            )
            _, private_key = mnemonic_to_private_key(self.seed_phrase)
            self.wallet_private_key = private_key
            self.wallet_public_key = self.wallet.public_key.hex()

        try:
            await asyncio.wait_for(_do_init(), timeout=timeout)
        finally:
            clear_mnemonic(self.seed_phrase)

    async def _init_wallet(self):
        forced_version = os.getenv("TON_WALLET_VERSION", "").strip().lower()
        if forced_version in {"v4r2", "w4r2"}:
            wallet = await WalletV4R2.from_mnemonic(self.provider, self.seed_phrase)
            return wallet, "v4r2"
        if forced_version in {"v5r1", "w5r1"}:
            wallet = await WalletV5R1.from_mnemonic(
                self.provider,
                self.seed_phrase,
                network_global_id=-239,
            )
            return wallet, "v5r1"
        wallet = await WalletV5R1.from_mnemonic(
            self.provider,
            self.seed_phrase,
            network_global_id=-239,
        )
        return wallet, "v5r1"

    def build_wallet_info(self) -> dict:
        state_init_cell = self.wallet.state_init.serialize()
        state_init_boc = base64.b64encode(
            state_init_cell.to_boc(has_idx=False)
        ).decode()
        return {
            "name": "ton_addr",
            "address": Address(self.wallet_address).to_str(is_user_friendly=False),
            "network": "-239",
            "publicKey": self.wallet_public_key,
            "walletStateInit": state_init_boc,
        }

    def prepare_connection(self, dapp_id: str):
        self.dapp_public_key = PublicKey(
            self._decode_dapp_id(dapp_id), encoder=RawEncoder
        )
        self.connection_box = Box(self.session_private_key, self.dapp_public_key)

    def _decode_dapp_id(self, dapp_id: str) -> bytes:
        if len(dapp_id) == 64:
            try:
                return bytes.fromhex(dapp_id)
            except ValueError:
                pass
        padding = (4 - (len(dapp_id) % 4)) % 4
        padded = dapp_id + ("=" * padding)
        try:
            return base64.urlsafe_b64decode(padded)
        except Exception:
            return base64.b64decode(padded)

    def build_proof_item(
        self, request: dict, app_domain: str, timestamp: int
    ) -> Optional[dict]:
        proof_request = None
        for item in request.get("items", []):
            if item.get("name") == "ton_proof":
                proof_request = item
                break
        if not proof_request:
            return None
        return build_ton_proof_item(
            wallet_address=self.wallet_address,
            wallet_private_key=self.wallet_private_key,
            payload=proof_request.get("payload"),
            domain=app_domain,
            timestamp=timestamp,
        )

    async def close(self, timeout: Optional[float] = None):
        async def _do_close():
            if self.provider:
                await self.provider.close_all()

        await asyncio.wait_for(_do_close(), timeout=timeout)
