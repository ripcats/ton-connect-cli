import base64
import binascii
import re
from typing import Dict, Optional, Iterable
from urllib.parse import unquote, urlparse, parse_qs

import orjson


TC_URL_REGEX = re.compile(r"^tc://[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+$")


def _json_loads(payload: str) -> dict:
    return orjson.loads(payload)


def validate_tc_url(tc_url: str) -> bool:
    if not tc_url or not TC_URL_REGEX.match(tc_url):
        return False
    parsed = urlparse(tc_url)
    if parsed.scheme != "tc" or not parsed.query:
        return False
    params = parse_qs(parsed.query)
    return "id" in params and "r" in params


def _b64decode_any(data: str) -> bytes:
    padding = (4 - (len(data) % 4)) % 4
    padded = data + ("=" * padding)
    try:
        return base64.urlsafe_b64decode(padded)
    except binascii.Error:
        return base64.b64decode(padded)


def parse_tc_url(tc_url: str) -> Dict:
    if not validate_tc_url(tc_url):
        raise ValueError("Invalid tc:// URL format")
    parsed_url = urlparse(tc_url)
    raw_params = {k: v[0] for k, v in parse_qs(parsed_url.query).items()}
    result = {
        "version": raw_params.get("v", "2"),
        "id": raw_params.get("id"),
        "return_url": raw_params.get("ret"),
    }
    raw_r = raw_params.get("r")
    if raw_r:
        decoded_r = unquote(raw_r)
        if decoded_r.strip().startswith("{"):
            result["request"] = _json_loads(decoded_r)
        else:
            request_payload = _b64decode_any(raw_r).decode("utf-8")
            result["request"] = _json_loads(request_payload)
    return result


def extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or url


def get_tc_domain(tc_url: str) -> Optional[str]:
    try:
        parsed = parse_tc_url(tc_url)
    except Exception:
        return None
    request = parsed.get("request", {})
    manifest_url = request.get("manifestUrl", "")
    if not manifest_url:
        return None
    return extract_domain(manifest_url)


def sanitize_domain(domain: str) -> Optional[str]:
    if not domain:
        return None
    candidate = domain.strip().lower()
    if not candidate:
        return None
    if "://" in candidate:
        parsed = urlparse(candidate)
        candidate = parsed.hostname or ""
    candidate = candidate.split("/")[0].split(":")[0].strip()
    if not candidate:
        return None
    if not re.match(r"^[a-z0-9.-]+$", candidate):
        return None
    return candidate


def sanitize_allowed_domains(domains: Optional[Iterable[str]]) -> Optional[set[str]]:
    cleaned = {d for d in (sanitize_domain(item) for item in (domains or [])) if d}
    return cleaned or None
