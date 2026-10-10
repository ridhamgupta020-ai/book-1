import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from bookings.models import Booking
from .firebase_auth import (
    FirebaseAccountConflict,
    FirebaseAuthUnavailable,
    InvalidFirebaseToken,
    verify_firebase_id_token,
)
from .forms import UserProfileUpdateForm, UserRegisterForm
from .models import UserProfile


logger = logging.getLogger(__name__)


class MyBookShowLoginView(LoginView):
    template_name = "users/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["firebase_web_config"] = settings.FIREBASE_WEB_CONFIG
        return context


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


@require_POST
def google_session_view(request):
    id_token = request.POST.get("id_token", "").strip()
    if not id_token:
        return JsonResponse({"error": "A Firebase ID token is required."}, status=400)

    try:
        claims = verify_firebase_id_token(id_token)
        user = _get_or_create_firebase_user(claims)
    except InvalidFirebaseToken:
        return JsonResponse(
            {"error": "Google sign-in could not be verified. Please try again."},
            status=401,
        )
    except FirebaseAccountConflict as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    except FirebaseAuthUnavailable:
        logger.exception("Firebase authentication is unavailable.")
        return JsonResponse(
            {"error": "Google sign-in is temporarily unavailable."}, status=503
        )
    except IntegrityError:
        uid = claims.get("uid", "")
        linked_profile = (
            UserProfile.objects.select_related("user")
            .filter(firebase_uid=uid)
            .first()
        )
        if linked_profile is None:
            logger.exception("Could not safely link a Firebase identity to a user.")
            return JsonResponse(
                {"error": "This Google account could not be linked safely."},
                status=409,
            )
        user = linked_profile.user

    if not user.is_active:
        return JsonResponse(
            {"error": "This account is inactive. Contact support for help."},
            status=403,
        )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = reverse("movies:home")
    response = JsonResponse({"redirect_url": next_url})
    response["Cache-Control"] = "no-store"
    return response


def _get_or_create_firebase_user(claims):
    uid = claims.get("uid")
    email = claims.get("email")
    firebase_claims = claims.get("firebase", {})

    if (
        not isinstance(uid, str)
        or not uid
        or not isinstance(email, str)
        or not email.strip()
        or claims.get("email_verified") is not True
        or not isinstance(firebase_claims, dict)
        or firebase_claims.get("sign_in_provider") != "google.com"
    ):
        raise InvalidFirebaseToken

    email = email.strip().lower()
    with transaction.atomic():
        profile = (
            UserProfile.objects.select_related("user")
            .select_for_update()
            .filter(firebase_uid=uid)
            .first()
        )
        if profile is not None:
            user = profile.user
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                raise FirebaseAccountConflict(
                    "This verified email is already attached to another account."
                )
        else:
            matching_users = list(
                User.objects.filter(email__iexact=email).order_by("pk")[:2]
            )
            if len(matching_users) > 1:
                raise FirebaseAccountConflict(
                    "Multiple accounts use this email. Contact support to link Google sign-in."
                )
            if matching_users:
                user = matching_users[0]
                profile, _ = UserProfile.objects.select_for_update().get_or_create(
                    user=user
                )
                if profile.firebase_uid and profile.firebase_uid != uid:
                    raise FirebaseAccountConflict(
                        "This account is already linked to a different Google account."
                    )
            else:
                base_username = slugify(email.split("@", 1)[0])[:120] or "google-user"
                safe_uid = slugify(uid)[:12] or "google-user"
                username = f"{base_username}-{safe_uid}"
                suffix = 1
                while User.objects.filter(username=username).exists():
                    suffix += 1
                    username = f"{base_username}-{safe_uid}-{suffix}"

                display_name = claims.get("name", "")
                if not isinstance(display_name, str):
                    display_name = ""
                display_name = display_name.strip()
                first_name, _, last_name = display_name.partition(" ")
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=first_name[:150],
                    last_name=last_name[:150],
                )
                profile, _ = UserProfile.objects.get_or_create(user=user)

        profile.firebase_uid = uid
        profile.save(update_fields=["firebase_uid", "updated_at"])
        if user.email != email:
            user.email = email
            user.save(update_fields=["email"])

    return user


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
