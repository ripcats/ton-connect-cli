from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TonConnectErrorCode(str, Enum):
    MNEMONIC_NOT_SPECIFIED = "MNEMONIC_NOT_SPECIFIED"
    INVALID_TC_URL = "INVALID_TC_URL"
    FORBIDDEN = "FORBIDDEN"
    WALLET_INIT_FAILED = "WALLET_INIT_FAILED"
    CONNECT_FAILED = "CONNECT_FAILED"
    BRIDGE_ERROR = "BRIDGE_ERROR"


class TonConnectResultCode(str, Enum):
    DAPP_CONNECTED = "DAPP_CONNECTED"
    DAPP_CONNECTED_FAILED = "DAPP_CONNECTED_FAILED"
    FORBIDDEN = "FORBIDDEN"


class WalletVersion(str, Enum):
    """
    Supported TON wallet contract versions.

    Use instead of the TON_WALLET_VERSION env-var string so that
    typos are caught at call-site rather than silently falling back
    to the default version at runtime.

    Example::

        client = TonConnectClient(wallet_version=WalletVersion.V4R2)
    """

    V4R2 = "v4r2"
    V5R1 = "v5r1"

    W4R2 = "v4r2"
    W5R1 = "v5r1"

    @classmethod
    def from_env(cls, raw: str) -> Optional["WalletVersion"]:
        """
        Parse the value of TON_WALLET_VERSION.

        Returns ``None`` when *raw* is empty/unset so the caller can
        apply a sensible default without special-casing empty strings.

        >>> WalletVersion.from_env("v4r2")
        <WalletVersion.V4R2: 'v4r2'>
        >>> WalletVersion.from_env("") is None
        True
        >>> WalletVersion.from_env("UNKNOWN")  # raises
        Traceback (most recent call last):
            ...
        ValueError: Unsupported wallet version: 'UNKNOWN'. Choose from: v4r2, v5r1
        """
        normalized = raw.strip().lower()
        if not normalized:
            return None
        for member in cls:
            if member.value == normalized:
                return member
        valid = ", ".join(sorted({m.value for m in cls}))
        raise ValueError(f"Unsupported wallet version: {raw!r}. Choose from: {valid}")

    @property
    def is_v5(self) -> bool:
        return self.value == "v5r1"

    @property
    def is_v4(self) -> bool:
        return self.value == "v4r2"


@dataclass(frozen=True)
class TonConnectResult:
    code: TonConnectResultCode
    data: Optional[dict] = None
    error_code: Optional[TonConnectErrorCode] = None
    error_message: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Shorthand: ``result.ok`` instead of comparing the enum."""
        return self.code == TonConnectResultCode.DAPP_CONNECTED


class TonConnectException(RuntimeError):
    def __init__(self, code: TonConnectErrorCode, message: str):
        super().__init__(message)
        self.code = code
