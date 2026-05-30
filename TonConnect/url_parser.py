import base64
import binascii
import re
from typing import Dict, Iterable, Optional
from urllib.parse import unquote, urlparse, parse_qs

import orjson


TC_URL_REGEX = re.compile(r"^tc://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+$")

_HOSTNAME_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")


def _json_loads(payload: str) -> dict:
    return orjson.loads(payload)


def _b64decode_any(data: str) -> bytes:
    """Decode base64 with or without padding, url-safe or standard alphabet."""
    padded = data + "=" * ((4 - len(data) % 4) % 4)
    try:
        return base64.urlsafe_b64decode(padded)
    except binascii.Error:
        return base64.b64decode(padded)


def validate_tc_url(tc_url: str) -> bool:
    """Return *True* if *tc_url* looks like a well-formed TonConnect URL."""
    if not tc_url or not TC_URL_REGEX.match(tc_url):
        return False
    parsed = urlparse(tc_url)
    if parsed.scheme != "tc" or not parsed.query:
        return False
    params = parse_qs(parsed.query)
    return "id" in params and "r" in params


def parse_tc_url(tc_url: str) -> Dict:
    """
    Parse a ``tc://`` URL into a structured dict.

    Returns::

        {
            "version": str,          # "2" when absent
            "id": str,               # dApp public key (hex or base64)
            "return_url": str|None,  # value of the "ret" param
            "request": dict,         # decoded "r" payload
        }

    Raises :class:`ValueError` for malformed URLs.
    """
    if not validate_tc_url(tc_url):
        raise ValueError(f"Invalid tc:// URL: {tc_url!r}")

    parsed_url = urlparse(tc_url)
    raw_params = {k: v[0] for k, v in parse_qs(parsed_url.query).items()}

    result: Dict = {
        "version": raw_params.get("v", "2"),
        "id": raw_params.get("id"),
        "return_url": raw_params.get("ret"),
    }

    raw_r = raw_params.get("r")
    if raw_r:
        decoded_r = unquote(raw_r)
        if decoded_r.lstrip().startswith("{"):
            result["request"] = _json_loads(decoded_r)
        else:
            payload = _b64decode_any(raw_r).decode("utf-8")
            result["request"] = _json_loads(payload)

    return result


def extract_domain(url: str) -> str:
    """Return the hostname from *url*, or *url* itself if parsing fails."""
    return urlparse(url).hostname or url


def get_tc_domain(tc_url: str) -> Optional[str]:
    """
    Extract the dApp domain from the ``manifestUrl`` inside a tc:// URL.

    Returns ``None`` when the URL is unparseable or the manifest URL is absent.
    """
    try:
        parsed = parse_tc_url(tc_url)
    except (ValueError, Exception):
        return None

    manifest_url = parsed.get("request", {}).get("manifestUrl", "")
    if not manifest_url:
        return None

    return extract_domain(manifest_url) or None


def sanitize_domain(domain: str) -> Optional[str]:
    """
    Normalise and validate a domain/URL string into a bare hostname.

    Strips scheme, path, port, and trailing whitespace; lower-cases the
    result; returns ``None`` for anything that doesn't look like a valid
    hostname.
    """
    if not domain:
        return None

    candidate = domain.strip().lower()

    if "://" in candidate:
        candidate = urlparse(candidate).hostname or ""

    candidate = candidate.split("/")[0].split(":")[0].strip()

    if not candidate:
        return None

    if not _HOSTNAME_RE.match(candidate):
        return None

    if candidate.startswith("-") or candidate.endswith("-"):
        return None
    if candidate.startswith(".") or candidate.endswith("."):
        return None

    return candidate


def sanitize_allowed_domains(domains: Optional[Iterable[str]]) -> Optional[set]:
    """
    Build a normalised allow-list from a sequence of domain strings.

    Returns ``None`` (not an empty set) when the result would be empty,
    so callers can distinguish "no filter" from "nothing passes".
    """
    cleaned = {
        d
        for d in (sanitize_domain(item) for item in (domains or []))
        if d
    }
    return cleaned if cleaned else None
