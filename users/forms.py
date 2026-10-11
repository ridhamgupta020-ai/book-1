from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile


class MyBookShowAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "class": "form-control bg-dark text-light border-secondary",
                "autocomplete": "username",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": "form-control bg-dark text-light border-secondary",
                "autocomplete": "current-password",
            }
        )


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=80, required=True)
    last_name = forms.CharField(max_length=80, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email


class UserProfileUpdateForm(forms.ModelForm):
    first_name = forms.CharField(max_length=80, required=True)
    last_name = forms.CharField(max_length=80, required=False)
    email = forms.EmailField(required=True)

    class Meta:
        model = UserProfile
        fields = ("phone_number", "preferred_city")
