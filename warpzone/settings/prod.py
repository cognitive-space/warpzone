print('Using Production Settings')

from warpzone.settings.base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False
DEBUG_SQL = False

STATIC_ROOT = BASE_DIR / 'static-compiled'
SECURE_SSL_REDIRECT = True

DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

AWS_ACCESS_KEY_ID = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
AWS_STORAGE_BUCKET_NAME = os.environ['AWS_STORAGE_BUCKET_NAME']
AWS_DEFAULT_ACL = 'private'
AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME')
AWS_QUERYSTRING_EXPIRE = 60 * 60
