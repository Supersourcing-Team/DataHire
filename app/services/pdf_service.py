import io
import logging
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)

class PDFService:
    def convert_html_to_pdf(self, html_content: str) -> bytes:
        """
        Converts an HTML string into PDF binary data using xhtml2pdf.
        """
        pdf_buffer = io.BytesIO()
        try:
            pisa_status = pisa.CreatePDF(
                src=html_content,
                dest=pdf_buffer
            )
            if pisa_status.err:
                logger.error("xhtml2pdf error during conversion: %s", pisa_status.err)
                raise Exception(f"Failed to convert HTML to PDF: {pisa_status.err} errors encountered")
            
            return pdf_buffer.getvalue()
        except Exception as e:
            logger.error("Error generating PDF from HTML: %s", str(e))
            raise e

pdf_service = PDFService()
