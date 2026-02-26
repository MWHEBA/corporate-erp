import os
from pathlib import Path
import environ

# قراءة متغيرات البيئة
env = environ.Env()
env_file = os.path.join(Path(__file__).resolve().parent.parent, ".env")
environ.Env.read_env(env_file)

# استيراد pymysql فقط إذا كنا نستخدم MySQL
if env("DB_ENGINE", default="sqlite") == "mysql":
    import pymysql

    pymysql.install_as_MySQLdb()

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ('celery_app',)
