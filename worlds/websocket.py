from importlib import import_module

from django import http
from django.conf import settings
from django.core.handlers.asgi import ASGIRequest
from django.contrib import auth

from asgiref.sync import sync_to_async

from loguru import logger

def add_websocket(app):
    async def websocket_app(scope, receive, send):
        if scope["type"] == "websocket":
            await logging_socket(scope, receive, send)
            return

        await app(scope, receive, send)

    return websocket_app


class AsyncWarpzoneRequest(ASGIRequest):
    def __init__(self, scope, body_file):
        scope['method'] = 'GET'
        super().__init__(scope, body_file)
        self.WS = http.QueryDict(scope.get('query_string', b'').decode())


def init_request(request):
    engine = import_module(settings.SESSION_ENGINE)
    session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
    request.session = engine.SessionStore(session_key)
    request.user = auth.get_user(request)


async def logging_socket(scope, receive, send):
    request = AsyncWarpzoneRequest(scope, None)
    await sync_to_async(init_request, thread_sensitive=True)(request)

    while 1:
        event = await receive()

        print(event)
        print(scope)
        print('User', request.user)

        if event['type'] == 'websocket.connect':
            logger.info('Websocket Connected')

            if not request.user.is_authenticated:
                logger.info('User not authenticated, Closing Socket')
                await send({'type': 'websocket.close'})
                return

        if event['type'] == 'websocket.disconnect':
            logger.info('Websocket Disconnected')

        if event['type'] == 'websocket.receive':
            logger.info('Received Message')
