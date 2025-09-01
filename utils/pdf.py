"""
PDF generation utilities for StudyBuddy
"""
import os
import tempfile
import markdown
from datetime import datetime
from fastapi import HTTPException
from utils.logger import get_logger

logger = get_logger("PDF", __name__)


async def generate_report_pdf(report_content: str, user_id: str, project_id: str) -> bytes:
    """
    Generate a PDF from report content using weasyprint
    
    Args:
        report_content: Markdown content of the report
        user_id: User ID for logging
        project_id: Project ID for logging
        
    Returns:
        PDF content as bytes
        
    Raises:
        HTTPException: If PDF generation fails
    """
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
        
        logger.info(f"[PDF] Generating PDF for user {user_id}, project {project_id}")
        
        # Convert markdown to HTML
        html_content = markdown.markdown(report_content, extensions=['codehilite', 'fenced_code'])
        
        # Create a complete HTML document with styling
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Study Report</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 40px 20px;
                }}
                h1, h2, h3, h4, h5, h6 {{
                    color: #2c3e50;
                    margin-top: 2em;
                    margin-bottom: 1em;
                }}
                h1 {{
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 10px;
                }}
                h2 {{
                    border-bottom: 1px solid #bdc3c7;
                    padding-bottom: 5px;
                }}
                code {{
                    background: #f8f9fa;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
                    font-size: 0.9em;
                }}
                pre {{
                    background: #2c3e50;
                    color: #ecf0f1;
                    padding: 20px;
                    border-radius: 8px;
                    overflow-x: auto;
                    margin: 1em 0;
                }}
                pre code {{
                    background: none;
                    padding: 0;
                    color: inherit;
                }}
                blockquote {{
                    border-left: 4px solid #3498db;
                    margin: 1em 0;
                    padding-left: 20px;
                    color: #7f8c8d;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 1em 0;
                }}
                th, td {{
                    border: 1px solid #bdc3c7;
                    padding: 12px;
                    text-align: left;
                }}
                th {{
                    background: #ecf0f1;
                    font-weight: 600;
                }}
                ul, ol {{
                    padding-left: 2em;
                }}
                li {{
                    margin: 0.5em 0;
                }}
                p {{
                    margin: 1em 0;
                }}
                .page-break {{
                    page-break-before: always;
                }}
                @page {{
                    margin: 2cm;
                    @bottom-center {{
                        content: "Page " counter(page);
                        font-size: 10px;
                        color: #7f8c8d;
                    }}
                }}
            </style>
        </head>
        <body>
            <h1>Study Report</h1>
            <p><em>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</em></p>
            <hr>
            {html_content}
        </body>
        </html>
        """
        
        # Generate PDF
        font_config = FontConfiguration()
        html_doc = HTML(string=full_html)
        css = CSS(string='', font_config=font_config)
        
        # Create temporary file for PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            pdf_path = tmp_file.name
        
        try:
            html_doc.write_pdf(pdf_path, stylesheets=[css], font_config=font_config)
            
            # Read the generated PDF
            with open(pdf_path, 'rb') as pdf_file:
                pdf_content = pdf_file.read()
            
            # Clean up temporary file
            os.unlink(pdf_path)
            
            logger.info(f"[PDF] Successfully generated PDF ({len(pdf_content)} bytes) for user {user_id}, project {project_id}")
            return pdf_content
            
        except Exception as e:
            # Clean up temporary file on error
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            raise e
            
    except ImportError:
        logger.error("[PDF] weasyprint not installed. Install with: pip install weasyprint")
        raise HTTPException(500, detail="PDF generation not available. Please install weasyprint.")
    except Exception as e:
        logger.error(f"[PDF] Failed to generate PDF: {e}")
        raise HTTPException(500, detail=f"Failed to generate PDF: {str(e)}")
