print('Using Development Settings')

import os
from warpzone.settings.base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

DEBUG_SQL = os.environ.get('DEBUG_SQL')
