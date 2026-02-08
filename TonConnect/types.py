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


@dataclass(frozen=True)
class TonConnectResult:
    code: TonConnectResultCode
    data: Optional[dict] = None
    error_code: Optional[TonConnectErrorCode] = None
    error_message: Optional[str] = None


class TonConnectException(RuntimeError):
    def __init__(self, code: TonConnectErrorCode, message: str):
        super().__init__(message)
        self.code = code
