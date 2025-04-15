from io import BytesIO
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.core.mail import EmailMessage

def render_to_pdf(template_src, context_data={}):
    template = get_template(template_src)
    html = template.render(context_data)
    result = BytesIO()

    pdf = pisa.pisaDocument(BytesIO(html.encode('UTF-8')), result)
    if not pdf.err:
        email = EmailMessage(
            subject='End of Day Report',
            body='Please find attached the end of day production report.',
            from_email='admin@techcity.co.zw',
            to=['cassymoyo@gmail.com', 'teddychinomona@gmail.com'],
        )

        # Attach PDF
        email.attach('end_of_day_report.pdf', result.getvalue(), 'application/pdf')
        email.send()
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None