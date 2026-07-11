from django.urls import path

from . import views

urlpatterns = [
    path("api/login", views.login_user),
    path("api/logout", views.logout_user),
    path("api/get_csrf_token", views.get_csrf_token),
]
