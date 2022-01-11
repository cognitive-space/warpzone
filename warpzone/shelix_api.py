from django.conf import settings

import httpx

class StarHelixApi:
    def __init__(self):
        self.client = httpx.Client(base_url=settings.SHELIX_URL)

    def start_log(self, app):
        resp = self.post('/stash/v1/start-log/', app=app)
        return resp.json()

    def end_log(self, log_id):
        resp = self.post('/stash/v1/end-log/', log_id=log_id)
        return resp.json()

    def post(self, url, **kwargs):
        kwargs['token'] = settings.SHELIX_TOKEN

        resp = self.client.post(url, data=kwargs)

        return resp
