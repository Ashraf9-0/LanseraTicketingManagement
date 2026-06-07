import qrcode
import qrcode.image.svg
from io import BytesIO
from django.core.files.base import ContentFile
from django.conf import settings


def generate_qr_code(ticket):
    """Generate a QR code for a ticket using its secure token."""
    qr_data = ticket.token
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    filename = f"ticket_{ticket.ticket_id}.png"
    ticket.qr_image.save(filename, ContentFile(buffer.read()), save=False)
    return ticket
