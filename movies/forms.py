from django import forms


class MovieFilterForm(forms.Form):
    SORT_CHOICES = [
        ("-release_date", "Newest Releases"),
        ("title", "Title (A–Z)"),
        ("duration_minutes", "Shortest Duration"),
    ]

    q = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "form-control bg-dark text-light border-secondary",
                "placeholder": "Search movies by title, cast, or director...",
            }
        ),
    )
    genre = forms.CharField(required=False, max_length=80)
    language = forms.CharField(required=False, max_length=80)
    status = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All Releases"),
            ("now_showing", "Now Showing"),
            ("coming_soon", "Coming Soon"),
        ],
    )
    sort = forms.ChoiceField(required=False, choices=SORT_CHOICES)
