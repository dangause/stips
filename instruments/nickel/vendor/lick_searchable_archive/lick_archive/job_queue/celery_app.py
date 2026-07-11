# This boiler plate code is taken from the celery docs at:
# https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html#using-celery-with-django
import os

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "lick_archive.lick_archive_site.settings"
)

from celery import Celery

app = Celery("lick_archive_site")


# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.

app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto load tasks from all registered Django apps
app.autodiscover_tasks(packages=["lick_archive.apps.ingest"])
