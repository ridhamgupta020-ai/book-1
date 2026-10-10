from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = "users"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path(
        "login/",
        views.MyBookShowLoginView.as_view(),
        name="login",
    ),
    path("google-session/", views.google_session_view, name="google_session"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="users/password_reset.html",
            success_url=reverse_lazy("users:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="users/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
]
