from html import escape
from io import BytesIO

import qrcode
from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def render_booking_ticket_pdf(booking) -> bytes:
    ticket_token = signing.dumps(
        {
            "booking_id": booking.pk,
            "payment_reference": booking.payment_transaction_id,
        },
        salt="bookings.ticket-verification",
    )
    verification_url = (
        f"{settings.SITE_URL}{reverse('bookings:verify_ticket')}?token={ticket_token}"
    )
    qr_buffer = BytesIO()
    qrcode.make(verification_url).save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TicketTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=26,
            textColor=colors.HexColor("#be123c"),
            alignment=TA_CENTER,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TicketValue",
            parent=styles["BodyText"],
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#1f2937"),
        )
    )

    def value(text):
        return Paragraph(escape(str(text)), styles["TicketValue"])

    def label(text):
        return Paragraph(f"<b>{escape(text)}</b>", styles["TicketValue"])

    seats = ", ".join(
        entry.show_seat.seat.label for entry in booking.booking_seats.all()
    )
    showtime = timezone.localtime(booking.show.start_time).strftime("%A, %d %B %Y at %I:%M %p")
    details = [
        [label("Movie"), value(booking.show.movie.title)],
        [label("Theater"), value(booking.show.screen.theatre.name)],
        [label("City"), value(booking.show.screen.theatre.city)],
        [label("Screen"), value(booking.show.screen.name)],
        [label("Showtime"), value(showtime)],
        [label("Seats"), value(seats)],
        [label("Booking ID"), value(booking.booking_reference)],
        [label("Payment reference"), value(booking.payment_transaction_id)],
        [label("Total paid"), value(f"INR {booking.total_amount}")],
    ]
    details_table = Table(details, colWidths=[1.35 * inch, 3.4 * inch])
    details_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ]
        )
    )
    qr_image = Image(qr_buffer, width=1.45 * inch, height=1.45 * inch)
    ticket_content = Table([[details_table, qr_image]], colWidths=[4.9 * inch, 1.6 * inch])
    ticket_content.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=f"MyBookShow Ticket {booking.booking_reference}",
    )
    document.build(
        [
            Paragraph("MYBOOKSHOW", styles["TicketTitle"]),
            Paragraph("Your movie ticket", styles["Heading2"]),
            Spacer(1, 0.2 * inch),
            ticket_content,
            Spacer(1, 0.25 * inch),
            Paragraph(
                "Present this ticket and QR code at the theater entrance. "
                "The QR code verifies this booking online.",
                styles["BodyText"],
            ),
        ]
    )
    return output.getvalue()
