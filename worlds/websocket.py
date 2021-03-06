import asyncio
import json
import multiprocessing as mp
from importlib import import_module

from django import http
from django.conf import settings
from django.core.cache import caches
from django.core.handlers.asgi import ASGIRequest
from django.contrib import auth
from django.utils import timezone

from asgiref.sync import sync_to_async

from loguru import logger

from worlds.models import Job, StreamLog


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


def get_log(job, pod, obj=False):
    return StreamLog.objects.filter(job=job, pod=pod).first()


async def watch_log_data(job, pod, send, log_queue):
    lines = 0
    wait = 0.1

    while 1:
        try:
            await asyncio.sleep(wait)
            wait = 3.0

            log = await sync_to_async(get_log, thread_sensitive=True)(job, pod)
            if log:
                if log.lines != lines:
                    lines_send = ''
                    line_array = []
                    for i in range(lines, log.lines):
                        line_array.append(f'{pod}-{i}')

                    if line_array:
                        line_dict = caches['default'].get_many(line_array)
                        msg_lines = ''
                        for l in line_array:
                            m = line_dict.get(l, None)
                            if m is not None:
                                msg_lines += m

                        if msg_lines:
                            msg = {'type': 'log', 'data': msg_lines}
                            await send({'type': 'websocket.send', 'text': json.dumps(msg)})

                    lines = log.lines

                if log.status in ['completed', 'failed']:
                    break

        except:
            import traceback
            traceback.print_exc()
            raise

        try:
            if log_queue.get_nowait():
                log_queue.task_done()
                caches['default'].set(f'shutdown-{pod}', 'shutdown', 60)
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
                logger.info('Sending job update: {} {}', jdata['id'], jdata['status'])
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

        if event['type'] == 'websocket.connect':
            logger.info('Websocket Connected')

            if not request.user.is_authenticated:
                logger.info('User not authenticated, Closing Socket')
                await send({'type': 'websocket.close'})
                return

            job_queue = asyncio.Queue()
            task = asyncio.create_task(watch_job_data(job, send, job_queue))

            if pod:
                log_queue = asyncio.Queue()
                log_task = asyncio.create_task(watch_log_data(job, pod, send, log_queue))

            await send({'type': 'websocket.accept'})
            connected = True

        if connected and event['type'] == 'websocket.disconnect':
            logger.info('Websocket Disconnected')
            await job_queue.put(True)
            await job_queue.join()
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
