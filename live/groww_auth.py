"""
Groww daily access token manager.

Usage in any script:
    from live.groww_auth import get_groww_client
    client = get_groww_client()   # auto-refreshes if expired

Token lifecycle:
  - GROWW_API_TOKEN    : permanent (exp ~2051), never changes
  - TOTP_TOKEN_SECRET  : permanent base32 secret, never changes
  - GROWW_ACCESS_TOKEN : expires daily at 6 AM IST, auto-regenerated here
"""

import base64
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import pyotp
from dotenv import load_dotenv
from growwapi import GrowwAPI

log = logging.getLogger(__name__)

_ENV_PATH = Path(__file__).parent.parent / ".env"


def _load_env() -> tuple[str, str, str]:
    load_dotenv(_ENV_PATH)
    api_token    = os.getenv("GROWW_API_TOKEN", "")
    totp_secret  = os.getenv("TOTP_TOKEN_SECRET", "")
    access_token = os.getenv("GROWW_ACCESS_TOKEN", "")
    if not api_token:
        raise EnvironmentError("GROWW_API_TOKEN missing in .env")
    if not totp_secret:
        raise EnvironmentError("TOTP_TOKEN_SECRET missing in .env")
    return api_token, totp_secret, access_token


def _is_token_valid(token: str) -> bool:
    """Decode JWT and check expiry with a 5-minute buffer."""
    if not token:
        return False
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        payload = parts[1] + "=" * (4 - len(parts[1]) % 4)
        data    = json.loads(base64.urlsafe_b64decode(payload))
        exp     = data.get("exp", 0)
        return time.time() < (exp - 300)   # 5-min buffer before expiry
    except Exception:
        return False


def _fetch_new_token(api_token: str, totp_secret: str) -> str:
    """Generate TOTP and call Groww to get a fresh access token."""
    otp       = pyotp.TOTP(totp_secret).now()
    secs_left = 30 - (int(time.time()) % 30)

    if secs_left < 3:
        log.info("OTP about to expire — waiting for next 30s window...")
        time.sleep(secs_left + 1)
        otp = pyotp.TOTP(totp_secret).now()

    log.info(f"Fetching new Groww access token (OTP: {otp})")
    token = GrowwAPI.get_access_token(api_key=api_token, totp=otp)
    log.info("New access token obtained")
    return token


def _save_token_to_env(token: str) -> None:
    """Write GROWW_ACCESS_TOKEN back into .env so it persists."""
    content    = _ENV_PATH.read_text()
    token_line = f"GROWW_ACCESS_TOKEN='{token}'"
    if "GROWW_ACCESS_TOKEN=" in content:
        content = re.sub(r"GROWW_ACCESS_TOKEN='[^']*'", token_line, content)
    else:
        content = content.rstrip() + f"\n{token_line}\n"
    _ENV_PATH.write_text(content)
    os.environ["GROWW_ACCESS_TOKEN"] = token   # update in-process too


def get_groww_client() -> GrowwAPI:
    """
    Return an authenticated GrowwAPI client, refreshing the token if needed.
    Call this once at startup — takes ~1s if token is fresh, ~2s if it needs refresh.
    """
    api_token, totp_secret, access_token = _load_env()

    if _is_token_valid(access_token):
        exp = json.loads(
            base64.urlsafe_b64decode(
                access_token.split(".")[1] + "=="
            )
        ).get("exp", 0)
        log.info(f"Groww token valid until {datetime.fromtimestamp(exp).strftime('%Y-%m-%d %H:%M')}")
    else:
        log.info("Groww access token expired or missing — refreshing...")
        access_token = _fetch_new_token(api_token, totp_secret)
        _save_token_to_env(access_token)

    return GrowwAPI(access_token)
