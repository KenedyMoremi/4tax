"""Only the configured auth service may assert USSD owner identities."""
from functools import lru_cache
from uuid import UUID

import jwt
from django.conf import settings
from django.views.decorators.debug import sensitive_variables


class AuthenticationFailure(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


@lru_cache(maxsize=4)
def jwks_client(url):
    return jwt.PyJWKClient(url, timeout=2, lifespan=300)


@sensitive_variables()
def authenticate_owner(request):
    issuer, url = settings.REGISTRATION_AUTH_ISSUER, settings.REGISTRATION_AUTH_JWKS_URL
    if not issuer or not url:
        raise AuthenticationFailure(503, 'SERVICE_UNAVAILABLE')
    authorization = request.headers.get('Authorization', '').split()
    if len(authorization) != 2 or authorization[0].lower() != 'bearer' or len(authorization[1]) > 8192:
        raise AuthenticationFailure(401, 'INVALID_TOKEN')
    token = authorization[1]
    try:
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str):
            raise jwt.InvalidTokenError()
        key = jwks_client(url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=['RS256'], issuer=issuer,
                            audience='registration-api',
                            options={'require': ['exp', 'iat', 'sub', 'iss', 'aud']})
        owner = UUID(claims['sub'])
    except jwt.PyJWKClientConnectionError:
        raise AuthenticationFailure(503, 'SERVICE_UNAVAILABLE') from None
    except (jwt.PyJWTError, ValueError, TypeError):
        raise AuthenticationFailure(401, 'INVALID_TOKEN') from None
    scope = claims.get('scope')
    if claims.get('kind') != 'owner' or not isinstance(scope, str) or 'businesses:create' not in scope.split():
        raise AuthenticationFailure(403, 'FORBIDDEN')
    return issuer, owner
