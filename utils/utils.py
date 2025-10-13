from io import BytesIO
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.core.mail import EmailMessage
from loguru import logger

def render_to_pdf(template_src, context_data={}):
    template = get_template(template_src)
    html = template.render(context_data)
    result = BytesIO()

    pdf = pisa.pisaDocument(BytesIO(html.encode('UTF-8')), result)
    if not pdf.err:
        try:
            email = EmailMessage(
                subject='End of Day Report',
                body='Please find attached End Of Day Summary.',
                from_email='chinomonateddym@gmail.com',
                to=['cassymyo@gmail.com', ''],
            )
            # Attach PDF
            email.attach('end_of_day_report.pdf', result.getvalue(), 'application/pdf')
            email.send()
            logger.success(f'Email Succesffully sent.')
        except Exception as e:
            print(e)
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None