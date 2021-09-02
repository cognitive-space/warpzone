import base64

from django.db import connection
from django.conf import settings
from django.contrib.auth import authenticate

from loguru import logger

class BasicAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'HTTP_AUTHORIZATION' in request.META and request.META['HTTP_AUTHORIZATION']:
            authorization_header = request.META['HTTP_AUTHORIZATION']
            splitted = authorization_header.split(' ')
            if len(splitted) == 2:
                auth_type, auth_string = splitted
                if 'basic' == auth_type.lower():
                    try:
                        b64_decoded = base64.b64decode(auth_string)
                        auth_string_decoded = b64_decoded.decode()

                    except:
                        pass

                    else:
                        splitted = auth_string_decoded.split(':')
                        if len(splitted) == 2:
                            username, password = splitted
                            user = authenticate(username=username, password=password)
                            if user:
                                request._cached_user = user

        return self.get_response(request)


class DebugMiddleWare:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.DEBUG:
            if settings.DEBUG_SQL:
                for q in connection.queries:
                    logger.info('Query: {}', q['sql'])
                    logger.info('Query Time: {}', q['time'])

            logger.info('Total Queries: {}', len(connection.queries))

        return response
