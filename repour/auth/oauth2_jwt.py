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

    try:
        token = jwt.decode(
            token,
            c["auth"]["oauth2_jwt"]["public_key"],
            algorithms=["RS256"],
            options=OPTIONS,
            issuer=c["auth"]["oauth2_jwt"]["token_issuer"],
        )
        logger.info("Got valid token!")
        return True
    except JWTError as e:
        logger.info("Got invalid token: " + str(e))
        return False
