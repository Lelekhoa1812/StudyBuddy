"""
PDF generation utilities for StudyBuddy
"""
import os
import tempfile
import markdown
import re
from datetime import datetime
from fastapi import HTTPException
from utils.logger import get_logger

logger = get_logger("PDF", __name__)


async def generate_report_pdf(report_content: str, user_id: str, project_id: str) -> bytes:
    """
    Generate a PDF from report content using reportlab
    
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
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from io import BytesIO
        
        logger.info(f"[PDF] Generating PDF for user {user_id}, project {project_id}")
        
        # Create a BytesIO buffer for the PDF
        buffer = BytesIO()
        
        # Create the PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18
        )
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#2c3e50'),
            borderWidth=1,
            borderColor=colors.HexColor('#3498db'),
            borderPadding=10
        )
        
        heading1_style = ParagraphStyle(
            'CustomHeading1',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.HexColor('#2c3e50')
        )
        
        heading2_style = ParagraphStyle(
            'CustomHeading2',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=10,
            spaceBefore=16,
            textColor=colors.HexColor('#2c3e50')
        )
        
        heading3_style = ParagraphStyle(
            'CustomHeading3',
            parent=styles['Heading3'],
            fontSize=14,
            spaceAfter=8,
            spaceBefore=12,
            textColor=colors.HexColor('#2c3e50')
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=6,
            leading=14
        )
        
        code_style = ParagraphStyle(
            'Code',
            parent=styles['Code'],
            fontSize=9,
            fontName='Courier',
            backColor=colors.HexColor('#f8f9fa'),
            borderColor=colors.HexColor('#dee2e6'),
            borderWidth=1,
            borderPadding=5,
            leftIndent=10,
            rightIndent=10
        )
        
        # Parse markdown content
        story = []
        
        # Add title
        story.append(Paragraph("Study Report", title_style))
        story.append(Paragraph(f"<i>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</i>", normal_style))
        story.append(Spacer(1, 20))
        
        # Simple markdown parser
        lines = report_content.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                story.append(Spacer(1, 6))
                i += 1
                continue
            
            # Headers
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                header_text = line.lstrip('# ').strip()
                
                if level == 1:
                    story.append(Paragraph(header_text, heading1_style))
                elif level == 2:
                    story.append(Paragraph(header_text, heading2_style))
                elif level == 3:
                    story.append(Paragraph(header_text, heading3_style))
                else:
                    story.append(Paragraph(header_text, normal_style))
            
            # Code blocks
            elif line.startswith('```'):
                # Collect code block
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                
                if code_lines:
                    code_text = '\n'.join(code_lines)
                    story.append(Paragraph(f"<font name='Courier'>{code_text}</font>", code_style))
            
            # Lists
            elif line.startswith('- ') or line.startswith('* '):
                list_text = line[2:].strip()
                story.append(Paragraph(f"• {list_text}", normal_style))
            
            # Numbered lists
            elif re.match(r'^\d+\.\s', line):
                list_text = re.sub(r'^\d+\.\s', '', line)
                story.append(Paragraph(f"• {list_text}", normal_style))
            
            # Blockquotes
            elif line.startswith('> '):
                quote_text = line[2:].strip()
                story.append(Paragraph(f"<i>{quote_text}</i>", normal_style))
            
            # Horizontal rules
            elif line.startswith('---') or line.startswith('***'):
                story.append(Spacer(1, 12))
                story.append(Paragraph("_" * 50, normal_style))
                story.append(Spacer(1, 12))
            
            # Regular paragraphs
            else:
                # Handle inline formatting
                formatted_text = line
                # Bold
                formatted_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', formatted_text)
                # Italic
                formatted_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', formatted_text)
                # Inline code
                formatted_text = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', formatted_text)
                
                story.append(Paragraph(formatted_text, normal_style))
            
            i += 1
        
        # Build PDF
        doc.build(story)
        
        # Get PDF content
        pdf_content = buffer.getvalue()
        buffer.close()
        
        logger.info(f"[PDF] Successfully generated PDF ({len(pdf_content)} bytes) for user {user_id}, project {project_id}")
        return pdf_content
            
    except ImportError:
        logger.error("[PDF] reportlab not installed. Install with: pip install reportlab")
        raise HTTPException(500, detail="PDF generation not available. Please install reportlab.")
    except Exception as e:
        logger.error(f"[PDF] Failed to generate PDF: {e}")
        raise HTTPException(500, detail=f"Failed to generate PDF: {str(e)}")
