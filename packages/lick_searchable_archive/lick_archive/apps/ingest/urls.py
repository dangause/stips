from django.urls import path

from . import views

urlpatterns = [
    path("ingest/notifications/", views.IngestNotifications.as_view()),
    path("ingest/counts/<path:ingest_path>", views.IngestCounts.as_view()),
]
