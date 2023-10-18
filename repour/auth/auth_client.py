# auth_client module is used to obtain the service account's access_token
#
# The only method you probably will call is `access_token`
#
# Requires the REPOUR_OIDC_SERVICE_ACCOUNT_SECRET env var to be set
#
import datetime
import os
from datetime import timedelta

import aiohttp

from repour.config import config

TOKEN_TIME_SKEW_SECONDS = 60


# Should be a dict with keys 'token' and 'expiry_date'
current_token = None


async def access_token():
    """
    Try to return the cached current token if present and not yet expired.
    Otherwise, try to get a new access token and update the cache
    """
    global current_token

    if current_token is None or is_expired(current_token):
        current_token = await get_new_access_token()

    return current_token["token"]


async def get_new_access_token():
    """
    Return a new access token dict containing the 'token' and the 'expiry_date'
    """

    c = await config.get_configuration()

    keycloak_url = (
        c["auth"]["oauth2_jwt"]["token_issuer"] + "/protocol/openid-connect/token"
    )
    client_id = c["auth"]["service_account"]["client_id"]
    client_secret = os.environ.get("REPOUR_OIDC_SERVICE_ACCOUNT_SECRET")

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(keycloak_url, data=data) as resp:
            resp_obj = await resp.json()
            return {
                "token": resp_obj["access_token"],
                "expiry_date": datetime.datetime.now()
                + timedelta(seconds=resp_obj["expires_in"]),
            }


def is_expired(current_token):
    """
    See if the current token is expired. If it's still valid but will expire soon (TOKEN_TIME_SKEW_SECONDS seconds),
    we'll just say it's expired
    """

    if current_token is None or "expiry_date" not in current_token:
        return True

    expiry_date = current_token["expiry_date"]
    time_delta = expiry_date - datetime.datetime.now()

    # if token has already expired or will expire in less than TOKEN_TIME_SKEW_SECONDS seconds, just say it's expired
    return time_delta < timedelta(seconds=TOKEN_TIME_SKEW_SECONDS)
