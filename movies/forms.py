from django import forms
from django.utils import timezone
from bookings.models import Booking
from .models import Review, ReviewReport


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
        required=False, min_value=0, max_value=5, decimal_places=1
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


class ReviewForm(forms.ModelForm):
    booking = forms.ModelChoiceField(
        queryset=Booking.objects.none(),
        help_text="Select a show where theater staff checked you in.",
    )

    class Meta:
        model = Review
        fields = ("booking", "rating", "title", "text")
        widgets = {
            "rating": forms.Select(choices=[(value, value) for value in range(1, 6)]),
            "text": forms.Textarea(attrs={"rows": 4, "maxlength": 3000}),
        }

    def __init__(self, user, movie, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.movie = movie
        self.fields["booking"].queryset = Booking.objects.filter(
            user=user,
            show__movie=movie,
            status=Booking.Status.CONFIRMED,
            payment_status=Booking.PaymentStatus.PAID,
            checked_in_at__isnull=False,
            show__end_time__lt=timezone.now(),
        ).order_by("-show__start_time")

    def save(self, commit=True):
        review = super().save(commit=False)
        review.user = self.user
        review.movie = self.movie
        if commit:
            review.save()
        return review


class ReviewReportForm(forms.ModelForm):
    class Meta:
        model = ReviewReport
        fields = ("reason", "explanation")
        widgets = {
            "reason": forms.Select(
                choices=[
                    ("spam", "Spam"),
                    ("abuse", "Abusive content"),
                    ("spoiler", "Unmarked spoilers"),
                    ("other", "Other policy concern"),
                ]
            ),
            "explanation": forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
        }
