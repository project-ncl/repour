# flake8: noqa
import logging

from jose import JWTError, jwt
from repour.config import config

logger = logging.getLogger(__name__)


async def verify_token(token):
    c = await config.get_configuration()
    logger.info("Got token!")

    OPTIONS = {
        "verify_signature": True,
        "verify_aud": False,
        "verify_iat": True,
        "verify_exp": True,
        "verify_nbf": True,
        "verify_iss": True,
        "verify_sub": False,
        "verify_jti": True,
        "verify_at_hash": True,
        "leeway": 0,
    }

    # the public key is obtained from <sso server>/auth/realms/<realm> :: the json public_key, and then you add the "---- begin public key" and "--- end public key" at the end.
    try:
        token = jwt.decode(
            token,
            c["auth"]["oauth2_jwt"]["public_key"],
            algorithms=["RS256"],
            options=OPTIONS,
            issuer=c["auth"]["oauth2_jwt"]["token_issuer"],
        )
        logger.info("Got valid token from " + token["preferred_username"])

        realm_roles = token["realm_access"]["roles"]

        allowed_roles = c["auth"]["allowed_roles"]

        for role in allowed_roles:
            if role in realm_roles:
                return True

        logger.error(
            "User doesn't have the required role to login: "
            + token["preferred_username"]
        )
        return False
    except JWTError as e:
        logger.info("Got invalid token: " + str(e))
        return False
