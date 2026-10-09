from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from bookings.models import Booking
from .forms import UserProfileUpdateForm, UserRegisterForm
from .models import UserProfile


def register_view(request):
    if request.user.is_authenticated:
        return redirect("movies:home")
    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to MyBookShow! Your account is ready.")
            return redirect("movies:home")
    else:
        form = UserRegisterForm()
    return render(request, "users/register.html", {"form": form})


@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = UserProfileUpdateForm(request.POST, instance=profile)
        if form.is_valid():
            request.user.first_name = form.cleaned_data["first_name"]
            request.user.last_name = form.cleaned_data["last_name"]
            request.user.email = form.cleaned_data["email"]
            request.user.save(update_fields=["first_name", "last_name", "email"])
            form.save()
            messages.success(request, "Your profile settings have been updated.")
            return redirect("users:profile")
    else:
        form = UserProfileUpdateForm(
            instance=profile,
            initial={
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "email": request.user.email,
            },
        )
    recent_bookings = (
        Booking.objects.filter(user=request.user)
        .select_related("show", "show__movie", "show__screen__theatre")[:10]
    )
    return render(
        request,
        "users/profile.html",
        {
            "form": form,
            "recent_bookings": recent_bookings,
        },
    )
