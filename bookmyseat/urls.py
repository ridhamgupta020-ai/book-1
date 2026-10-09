"""URL Configuration for MyBookShow."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "MyBookShow Administration"
admin.site.site_title = "MyBookShow Admin Portal"
admin.site.index_title = "Cinema, Showtime & Reservation Management"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("users/", include("users.urls", namespace="users")),
    path("bookings/", include("bookings.urls", namespace="bookings")),
    path("", include("movies.urls", namespace="movies")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
