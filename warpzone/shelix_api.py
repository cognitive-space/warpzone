from django.conf import settings

import httpx

class StarHelixApi:
    def __init__(self):
        self.client = httpx.Client(base_url=settings.SHELIX_URL)

    @classmethod
    def start_log(cls, app):
        self = cls()
        resp = self.post('/stash/v1/start-log/', app=app)
        return resp.json()

    @classmethod
    def end_log(cls, log_id):
        self = cls()
        resp = self.post('/stash/v1/end-log/', log_id=log_id)
        print('RESP', resp)
        return resp.json()

    @classmethod
    def save_log(cls, log_id, text):
        self = cls()
        resp = self.post('/stash/v1/save-log/', log_id=log_id, logs=text)
        return resp.json()

    def post(self, url, **kwargs):
        kwargs['token'] = settings.SHELIX_TOKEN

        resp = self.client.post(url, data=kwargs)

        return resp
