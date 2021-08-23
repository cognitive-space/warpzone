web: gunicorn warpzone.asgi:application -k uvicorn.workers.UvicornWorker --max-requests 5000
worker1: python manage.py run_huey
worker2: python manage.py run_huey
worker3: python manage.py run_huey
