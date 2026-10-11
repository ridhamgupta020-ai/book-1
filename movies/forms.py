from django import forms


class MovieFilterForm(forms.Form):
    SORT_CHOICES = [
        ("popularity", "Most Popular"),
        ("-release_date", "Newest Releases"),
        ("-rating", "Top Rated"),
        ("ticket_price", "Lowest Ticket Price"),
        ("-ticket_price", "Highest Ticket Price"),
    ]

    q = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(
            attrs={
                "class": "form-control bg-dark text-light border-secondary",
                "placeholder": "Search movies by title...",
            }
        ),
    )
    genre = forms.CharField(required=False, max_length=80)
    language = forms.CharField(required=False, max_length=80)
    city = forms.CharField(required=False, max_length=100)
    theatre = forms.IntegerField(required=False, min_value=1)
    release_from = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    release_to = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    min_rating = forms.DecimalField(
        required=False, min_value=0, max_value=10, decimal_places=1
    )
    showtime = forms.ChoiceField(
        required=False,
        choices=[
            ("", "Any Showtime"),
            ("morning", "Morning (before noon)"),
            ("afternoon", "Afternoon (12–5 PM)"),
            ("evening", "Evening (after 5 PM)"),
        ],
    )
    status = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All Releases"),
            ("now_showing", "Now Showing"),
            ("coming_soon", "Coming Soon"),
        ],
    )
    sort = forms.ChoiceField(
        required=False, choices=SORT_CHOICES, initial="-release_date"
    )

    def clean(self):
        cleaned_data = super().clean()
        release_from = cleaned_data.get("release_from")
        release_to = cleaned_data.get("release_to")
        if release_from and release_to and release_from > release_to:
            self.add_error("release_to", "End date must be on or after start date.")
        return cleaned_data
