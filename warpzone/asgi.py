"""
ASGI config for warpzone project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import os

import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'warpzone.settings.dev')
django.setup()

from worlds.websocket import add_websocket

application = get_asgi_application()
application = add_websocket(application)
