import base64
import hashlib
import struct
from typing import Optional

from pytoniq_core import Address
from pytoniq_core.crypto.signature import sign_message


def build_ton_proof_message(
    payload: bytes, domain: str, address: str, timestamp: int
) -> bytes:
    addr = Address(address)
    domain_bytes = domain.encode()
    addr_bytes = struct.pack("<i", addr.wc) + addr.hash_part
    domain_part = struct.pack("<I", len(domain_bytes)) + domain_bytes
    time_part = struct.pack("<Q", timestamp)
    return b"ton-proof-item-v2/" + addr_bytes + domain_part + time_part + payload


def build_ton_proof_item(
    wallet_address: str,
    wallet_private_key,
    payload: Optional[str],
    domain: str,
    timestamp: int,
) -> Optional[dict]:
    if not payload:
        return None
    proof_message = build_ton_proof_message(
        payload=payload.encode(),
        domain=domain,
        address=wallet_address,
        timestamp=timestamp,
    )
    inner_hash = hashlib.sha256(proof_message).digest()
    sign_payload = b"\xff\xff" + b"ton-connect" + inner_hash
    final_hash = hashlib.sha256(sign_payload).digest()
    proof_signature = sign_message(final_hash, wallet_private_key)
    return {
        "name": "ton_proof",
        "proof": {
            "timestamp": timestamp,
            "domain": {
                "lengthBytes": len(domain.encode()),
                "length_bytes": len(domain.encode()),
                "value": domain,
            },
            "signature": base64.b64encode(proof_signature).decode(),
            "payload": payload,
        },
    }
