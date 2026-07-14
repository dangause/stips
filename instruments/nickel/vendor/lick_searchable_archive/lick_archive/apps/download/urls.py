from django.urls import path

from . import views

urlpatterns = [
    path("data/<path:file>", views.DownloadSingleView.as_view()),
    path("api/download", views.DownloadMultiView.as_view()),
]
