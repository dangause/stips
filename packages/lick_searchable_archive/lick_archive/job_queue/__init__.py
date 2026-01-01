# Make sure celery app is loaded for shared tasks

from .celery_app import app as celery_app

__all__ = "celery_app"
