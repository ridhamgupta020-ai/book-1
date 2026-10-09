from django import forms


class SeatSelectionForm(forms.Form):
    seat_ids = forms.CharField(
        required=True,
        help_text="Comma-separated ShowSeat IDs selected by the user.",
    )

    def clean_seat_ids(self) -> list[int]:
        raw = self.cleaned_data.get("seat_ids", "")
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            raise forms.ValidationError("Please select at least one seat.")
        try:
            ids = [int(p) for p in parts]
        except ValueError as exc:
            raise forms.ValidationError("Invalid seat identifier format.") from exc
        if len(ids) > 10:
            raise forms.ValidationError("You can book at most 10 seats per booking.")
        return ids
