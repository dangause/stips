from django.urls import path

from . import views

urlpatterns = [
    path("data/", views.QueryView.as_view()),
    path("data/<path:file>/header", views.HeaderView.as_view()),
]
