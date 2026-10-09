from django.urls import path
from . import views

app_name = "movies"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("movies/", views.movie_list_view, name="movie_list"),
    path("movies/<slug:slug>/", views.movie_detail_view, name="movie_detail"),
    path("theatres/", views.theatre_list_view, name="theatre_list"),
]
