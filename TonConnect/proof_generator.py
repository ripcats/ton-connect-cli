import base64
import hashlib
import struct
from typing import Optional

from pytoniq_core import Address
from pytoniq_core.crypto.signature import sign_message


def build_ton_proof_message(
    payload: bytes, domain: str, address: str, timestamp: int
) -> bytes:
    """
    Assemble the raw bytes that are hashed to produce a ``ton_proof`` signature.

    The layout follows the TonConnect 2.0 spec::

        "ton-proof-item-v2/"
        + workchain (int32-le)
        + address hash_part (32 bytes)
        + domain length (uint32-le)
        + domain (UTF-8)
        + timestamp (uint64-le)
        + payload

    :param payload: Raw proof payload bytes (usually ``payload_str.encode()``).
    :param domain: dApp hostname, e.g. ``"app.dedust.io"``.
    :param address: Wallet address in any form accepted by :class:`pytoniq_core.Address`.
    :param timestamp: Unix timestamp at the moment of signing.
    :returns: Concatenated proof message bytes ready to be SHA-256 hashed.
    """
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
    """
    Sign a TonConnect proof request and return the ``ton_proof`` item dict.

    Returns ``None`` when *payload* is empty or ``None``, which signals the
    caller that the dApp did not request a proof (``ton_proof`` item absent
    from the connect request).

    The signing pipeline:

    1. Build the canonical proof message via :func:`build_ton_proof_message`.
    2. SHA-256 hash the message → *inner_hash*.
    3. Prepend the TonConnect magic prefix ``\\xff\\xff`` + ``"ton-connect"``
       and hash again → *final_hash*.
    4. Sign *final_hash* with the wallet's Ed25519 private key.

    :param wallet_address: Wallet address string (any format accepted by pytoniq_core).
    :param wallet_private_key: Ed25519 private key bytes as returned by
        ``mnemonic_to_private_key``.
    :param payload: Proof payload string from the dApp connect request, or ``None``.
    :param domain: dApp domain used in the proof message.
    :param timestamp: Unix timestamp; should match the one in the connect event.
    :returns: ``ton_proof`` item dict ready to be included in the connect event
        payload, or ``None`` if no proof was requested.
    """
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
