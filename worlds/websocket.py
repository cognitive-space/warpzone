import asyncio
import json
from importlib import import_module

from django import http
from django.conf import settings
from django.core.handlers.asgi import ASGIRequest
from django.contrib import auth
from django.utils import timezone

from asgiref.sync import sync_to_async

from loguru import logger

from worlds.models import Job


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


def get_job(jid, obj=False):
    job = Job.objects.filter(id=jid).first()
    if job:
        if obj:
            return job

        return job.to_json()

    return {}


async def watch_log(jid, pod, send, queue):
    job = await sync_to_async(get_job, thread_sensitive=True)(jid)
    if job:
        for event in job.watch_pod(pod):
            msg = {'type': 'loj', 'data': event}
            await send({'type': 'websocket.send', 'text': json.dumps(msg)})

            try:
                if queue.get_nowait():
                    queue.task_done()
                    return

            except asyncio.QueueEmpty:
                pass


async def watch_job_data(job, send, queue):
    jdata = await sync_to_async(get_job, thread_sensitive=True)(job)
    last = timezone.now()

    while 1:
        await asyncio.sleep(0.1)
        now = timezone.now()
        diff = now - last
        if diff.total_seconds() > 5:
            last = now
            new_data = await sync_to_async(get_job, thread_sensitive=True)(job)
            if new_data['modified'] != jdata['modified']:
                jdata = new_data
                msg = {'type': 'job', 'data': jdata}
                await send({'type': 'websocket.send', 'text': json.dumps(msg)})

        try:
            if queue.get_nowait():
                queue.task_done()
                return

        except asyncio.QueueEmpty:
            pass


async def logging_socket(scope, receive, send):
    request = AsyncWarpzoneRequest(scope, None)
    await sync_to_async(init_request, thread_sensitive=True)(request)
    task = None
    log_task = None
    log_queue = None
    connected = False

    while 1:
        event = await receive()
        job = request.WS.get('job')
        pod = request.WS.get('pod')
        print('Web Socket', request.user, job, pod)

        if event['type'] == 'websocket.connect':
            logger.info('Websocket Connected')

            if not request.user.is_authenticated:
                logger.info('User not authenticated, Closing Socket')
                await send({'type': 'websocket.close'})
                return

            queue = asyncio.Queue()
            task = asyncio.create_task(watch_job_data(job, send, queue))

            if pod:
                log_queue = asyncio.Queue()
                log_task = asyncio.create_task(watch_log(job, pod, send, log_queue))

            await send({'type': 'websocket.accept'})
            connected = True

        if connected and event['type'] == 'websocket.disconnect':
            logger.info('Websocket Disconnected')
            await queue.put(True)
            await queue.join()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

            if log_queue:
                await log_queue.put(True)
                await log_queue.join()
                log_task.cancel()
                await asyncio.gather(log_task, return_exceptions=True)

            return

        if connected and event['type'] == 'websocket.receive':
            logger.info('Received Message')
