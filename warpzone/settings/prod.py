print('Using Production Settings')

from warpzone.settings.base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

STATIC_ROOT = BASE_DIR / 'static-compiled'
