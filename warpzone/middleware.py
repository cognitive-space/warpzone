import base64

from django.contrib.auth import authenticate


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
