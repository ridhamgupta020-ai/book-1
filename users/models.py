from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    firebase_uid = models.CharField(
        max_length=128, unique=True, null=True, blank=True
    )
    phone_number = models.CharField(max_length=20, blank=True, default="")
    preferred_city = models.CharField(max_length=80, default="Mumbai")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile({self.user.username})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
