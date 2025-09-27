"""
PDF generation utilities for StudyBuddy
"""
import os
import tempfile
import markdown
import re
from datetime import datetime
from typing import List, Dict
from fastapi import HTTPException
from utils.logger import get_logger

logger = get_logger("PDF", __name__)


async def _parse_markdown_content(content: str, heading1_style, heading2_style, heading3_style, normal_style, code_style):
    """
    Enhanced markdown parser that properly handles bold/italic formatting
    """
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import inch
    
    story = []
    lines = content.split('\n')
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
            header_text = _format_inline_markdown(header_text)
            
            if level == 1:
                story.append(Paragraph(header_text, heading1_style))
            elif level == 2:
                story.append(Paragraph(header_text, heading2_style))
            elif level == 3:
                story.append(Paragraph(header_text, heading3_style))
            else:
                story.append(Paragraph(header_text, normal_style))
        
        # Code blocks with language detection
        elif line.startswith('```'):
            # Extract language if specified
            language = line[3:].strip() if len(line) > 3 else 'text'
            
            # Auto-detect language if not specified
            if language == 'text':
                language = _detect_language_from_content(lines, i)
            
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            
            if code_lines:
                # Mermaid diagrams → render via Kroki PNG for PDF with retry logic
                if language.lower() == 'mermaid':
                    try:
                        from reportlab.platypus import Image, Spacer
                        mermaid_code = '\n'.join(code_lines)
                        # Use retry logic from diagram.py
                        from helpers.diagram import _render_mermaid_with_retry
                        img_bytes = await _render_mermaid_with_retry(mermaid_code)
                        
                        if img_bytes and len(img_bytes) > 0:
                            import io
                            img = Image(io.BytesIO(img_bytes))
                            # Fit within page width (~6 inches after margins)
                            max_width = 6.0 * inch
                            if img.drawWidth > max_width:
                                scale = max_width / float(img.drawWidth)
                                img.drawWidth = max_width
                                img.drawHeight = img.drawHeight * scale
                            story.append(img)
                            story.append(Spacer(1, 12))
                            i += 1
                            continue
                        else:
                            logger.warning("[PDF] Mermaid render returned empty image after retries, falling back to code block")
                    except Exception as me:
                        logger.warning(f"[PDF] Mermaid render failed after retries, falling back to code block: {me}")
                    
                    # Fallback: render as code block with mermaid syntax
                    from reportlab.platypus import XPreformatted, Paragraph
                    raw_code = '\n'.join(code_lines)
                    raw_code = raw_code.replace('\t', '    ')
                    raw_code = raw_code.replace('\r\n', '\n').replace('\r', '\n')
                    raw_code = re.sub(r'[^\x09\x0A\x20-\x7E]', '', raw_code)
                    escaped = raw_code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    lang_header = f"<font color='#9aa5b1' size='8'>[MERMAID DIAGRAM]</font>"
                    story.append(Paragraph(lang_header, code_style))
                    story.append(XPreformatted(escaped, code_style))
                    i += 1
                    continue

                from reportlab.platypus import XPreformatted, Paragraph
                # Join and sanitize code content: expand tabs, remove control chars that render as squares
                raw_code = '\n'.join(code_lines)
                raw_code = raw_code.replace('\t', '    ')
                raw_code = raw_code.replace('\r\n', '\n').replace('\r', '\n')
                # Strip non-printable except tab/newline
                raw_code = re.sub(r'[^\x09\x0A\x20-\x7E]', '', raw_code)

                # Escape for XML and apply lightweight syntax highlighting
                escaped = raw_code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                highlighted = _apply_syntax_highlight(escaped, language)

                # Add a small language header, then render highlighted code with XPreformatted to preserve spacing
                lang_header = f"<font color='#9aa5b1' size='8'>[{language.upper()}]</font>"
                story.append(Paragraph(lang_header, code_style))
                story.append(XPreformatted(highlighted, code_style))
        
        # Lists (including nested)
        elif line.startswith('- ') or line.startswith('* '):
            # Count indentation level
            indent_level = len(line) - len(line.lstrip())
            list_text = line[2:].strip()
            list_text = _format_inline_markdown(list_text)
            
            # Add indentation based on level
            indent = "&nbsp;" * (indent_level // 2) if indent_level > 0 else ""
            story.append(Paragraph(f"{indent}• {list_text}", normal_style))
        
        # Numbered lists (including nested)
        elif re.match(r'^\d+\.\s', line):
            # Count indentation level
            indent_level = len(line) - len(line.lstrip())
            list_text = re.sub(r'^\d+\.\s', '', line)
            list_text = _format_inline_markdown(list_text)
            
            # Add indentation based on level
            indent = "&nbsp;" * (indent_level // 2) if indent_level > 0 else ""
            story.append(Paragraph(f"{indent}• {list_text}", normal_style))
        
        # Blockquotes
        elif line.startswith('> '):
            quote_text = line[2:].strip()
            quote_text = _format_inline_markdown(quote_text)
            story.append(Paragraph(f"<i>{quote_text}</i>", normal_style))
        
        # Horizontal rules
        elif line.startswith('---') or line.startswith('***'):
            story.append(Spacer(1, 12))
            story.append(Paragraph("_" * 50, normal_style))
            story.append(Spacer(1, 12))
        
        # Regular paragraphs - collect multi-line paragraphs
        else:
            paragraph_lines = [line]
            i += 1
            
            # Collect continuation lines until we hit a blank line or another block type
            while i < len(lines):
                next_line = lines[i].strip()
                
                # Stop if we hit a blank line
                if not next_line:
                    break
                
                # Stop if we hit a new block type
                if (next_line.startswith('#') or 
                    next_line.startswith('```') or 
                    next_line.startswith('- ') or 
                    next_line.startswith('* ') or 
                    re.match(r'^\d+\.\s', next_line) or
                    next_line.startswith('> ') or
                    next_line.startswith('---') or 
                    next_line.startswith('***')):
                    break
                
                paragraph_lines.append(next_line)
                i += 1
            
            # Process the complete paragraph
            paragraph_text = ' '.join(paragraph_lines)
            formatted_text = _format_inline_markdown(paragraph_text)
            story.append(Paragraph(formatted_text, normal_style))
            continue  # Don't increment i again since we already did it in the loop
        
        i += 1
    
    return story


def _detect_language_from_content(lines: list, start_index: int) -> str:
    """
    Auto-detect programming language from code content
    """
    # Look at the next few lines to detect language
    sample_lines = []
    for i in range(start_index + 1, min(start_index + 10, len(lines))):
        if lines[i].strip().startswith('```'):
            break
        sample_lines.append(lines[i])
    
    sample_text = '\n'.join(sample_lines)
    
    # Python detection
    if (re.search(r'\bdef\s+\w+', sample_text) or 
        re.search(r'\bclass\s+\w+', sample_text) or
        re.search(r'\bimport\s+\w+', sample_text) or
        re.search(r'\bfrom\s+\w+', sample_text)):
        return 'python'
    
    # JavaScript detection
    if (re.search(r'\bfunction\s+\w+', sample_text) or
        re.search(r'\bvar\s+\w+', sample_text) or
        re.search(r'\blet\s+\w+', sample_text) or
        re.search(r'\bconst\s+\w+', sample_text) or
        re.search(r'=>', sample_text)):
        return 'javascript'
    
    # Java detection
    if (re.search(r'\bpublic\s+class', sample_text) or
        re.search(r'\bprivate\s+\w+', sample_text) or
        re.search(r'\bSystem\.out\.print', sample_text) or
        re.search(r'\bimport\s+java\.', sample_text)):
        return 'java'
    
    # JSON detection
    if (re.search(r'^\s*[{}]', sample_text) or
        re.search(r'"[^"]*"\s*:', sample_text) or
        re.search(r'\btrue\b|\bfalse\b|\bnull\b', sample_text)):
        return 'json'
    
    # XML/HTML detection
    if (re.search(r'<[^>]+>', sample_text) or
        re.search(r'&lt;[^&gt;]+&gt;', sample_text)):
        return 'xml'
    
    # SQL detection
    if (re.search(r'\bSELECT\b', sample_text, re.IGNORECASE) or
        re.search(r'\bFROM\b', sample_text, re.IGNORECASE) or
        re.search(r'\bWHERE\b', sample_text, re.IGNORECASE) or
        re.search(r'\bINSERT\b', sample_text, re.IGNORECASE)):
        return 'sql'
    
    # YAML detection
    if (re.search(r'^\s*\w+:', sample_text) or
        re.search(r'^\s*-\s+', sample_text)):
        return 'yaml'
    
    # Bash detection
    if (re.search(r'^\s*#!', sample_text) or
        re.search(r'\$\w+', sample_text) or
        re.search(r'^\s*\w+.*\|', sample_text)):
        return 'bash'
    
    return 'text'


def _format_code_block(code_text: str, language: str) -> str:
    """
    Deprecated: We now render code blocks with Preformatted to avoid paragraph parser errors.
    Kept for compatibility if referenced elsewhere; returns escaped plain text.
    """
    code_text = code_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return f"<font name='Courier' size='9'>{code_text}</font>"


def _highlight_python(code: str) -> str:
    """Python syntax highlighting"""
    # Keywords
    keywords = ['def', 'class', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'finally', 
               'import', 'from', 'as', 'with', 'return', 'yield', 'lambda', 'and', 'or', 'not', 
               'in', 'is', 'True', 'False', 'None', 'pass', 'break', 'continue', 'raise', 'assert']
    
    # Built-in functions
    builtins = ['print', 'len', 'str', 'int', 'float', 'list', 'dict', 'tuple', 'set', 'range',
                'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed', 'open', 'input']
    
    # String literals
    code = re.sub(r'("""[\s\S]*?""")', r'<font color="#008000">\1</font>', code)  # Triple quotes
    code = re.sub(r'(".*?")', r'<font color="#008000">\1</font>', code)  # Double quotes
    code = re.sub(r"('''[\s\S]*?''')", r'<font color="#008000">\1</font>', code)  # Triple single quotes
    code = re.sub(r"('.*?')", r'<font color="#008000">\1</font>', code)  # Single quotes
    
    # Comments
    code = re.sub(r'(#.*?)$', r'<font color="#808080">\1</font>', code, flags=re.MULTILINE)
    
    # Keywords
    for keyword in keywords:
        code = re.sub(r'\b(' + keyword + r')\b', r'<font color="#0000FF"><b>\1</b></font>', code)
    
    # Built-in functions
    for builtin in builtins:
        code = re.sub(r'\b(' + builtin + r')\b', r'<font color="#800080">\1</font>', code)
    
    # Numbers
    code = re.sub(r'\b(\d+\.?\d*)\b', r'<font color="#FF0000">\1</font>', code)
    
    return f"<font name='Courier' size='9'>{code}</font>"


def _highlight_json(code: str) -> str:
    """JSON syntax highlighting"""
    # Strings
    code = re.sub(r'(".*?")', r'<font color="#008000">\1</font>', code)
    
    # Numbers
    code = re.sub(r'\b(\d+\.?\d*)\b', r'<font color="#FF0000">\1</font>', code)
    
    # Keywords
    code = re.sub(r'\b(true|false|null)\b', r'<font color="#0000FF"><b>\1</b></font>', code)
    
    # Punctuation
    code = re.sub(r'([{}[\]])', r'<font color="#800080"><b>\1</b></font>', code)
    code = re.sub(r'([,])', r'<font color="#800080">\1</font>', code)
    
    return f"<font name='Courier' size='9'>{code}</font>"


def _highlight_xml(code: str) -> str:
    """XML/HTML syntax highlighting"""
    # Tags
    code = re.sub(r'(&lt;[^&gt;]*&gt;)', r'<font color="#0000FF"><b>\1</b></font>', code)
    
    # Attributes
    code = re.sub(r'(\w+)=', r'<font color="#800080">\1</font>=', code)
    
    # Attribute values
    code = re.sub(r'="([^"]*)"', r'="<font color="#008000">\1</font>"', code)
    
    # Comments
    code = re.sub(r'(&lt;!--[\s\S]*?--&gt;)', r'<font color="#808080">\1</font>', code)
    
    return f"<font name='Courier' size='9'>{code}</font>"


def _highlight_java(code: str) -> str:
    """Java syntax highlighting"""
    # Keywords
    keywords = ['public', 'private', 'protected', 'static', 'final', 'class', 'interface', 'extends', 
               'implements', 'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'break', 'continue',
               'return', 'try', 'catch', 'finally', 'throw', 'throws', 'new', 'this', 'super', 'import',
               'package', 'void', 'int', 'long', 'float', 'double', 'boolean', 'char', 'byte', 'short',
               'true', 'false', 'null']
    
    # String literals
    code = re.sub(r'(".*?")', r'<font color="#008000">\1</font>', code)
    code = re.sub(r"('.*?')", r'<font color="#008000">\1</font>', code)
    
    # Comments
    code = re.sub(r'(//.*?)$', r'<font color="#808080">\1</font>', code, flags=re.MULTILINE)
    code = re.sub(r'(/\*[\s\S]*?\*/)', r'<font color="#808080">\1</font>', code)
    
    # Keywords
    for keyword in keywords:
        code = re.sub(r'\b(' + keyword + r')\b', r'<font color="#0000FF"><b>\1</b></font>', code)
    
    # Numbers
    code = re.sub(r'\b(\d+\.?\d*[fFdDlL]?)\b', r'<font color="#FF0000">\1</font>', code)
    
    return f"<font name='Courier' size='9'>{code}</font>"


def _highlight_javascript(code: str) -> str:
    """JavaScript syntax highlighting"""
    # Keywords
    keywords = ['function', 'var', 'let', 'const', 'if', 'else', 'for', 'while', 'do', 'switch', 
               'case', 'break', 'continue', 'return', 'try', 'catch', 'finally', 'throw', 'new', 
               'this', 'typeof', 'instanceof', 'true', 'false', 'null', 'undefined', 'async', 'await']
    
    # String literals
    code = re.sub(r'(".*?")', r'<font color="#008000">\1</font>', code)
    code = re.sub(r"('.*?')", r'<font color="#008000">\1</font>', code)
    code = re.sub(r'(`.*?`)', r'<font color="#008000">\1</font>', code)  # Template literals
    
    # Comments
    code = re.sub(r'(//.*?)$', r'<font color="#808080">\1</font>', code, flags=re.MULTILINE)
    code = re.sub(r'(/\*[\s\S]*?\*/)', r'<font color="#808080">\1</font>', code)
    
    # Keywords
    for keyword in keywords:
        code = re.sub(r'\b(' + keyword + r')\b', r'<font color="#0000FF"><b>\1</b></font>', code)
    
    # Numbers
    code = re.sub(r'\b(\d+\.?\d*)\b', r'<font color="#FF0000">\1</font>', code)
    
    return f"<font name='Courier' size='9'>{code}</font>"


def _highlight_sql(code: str) -> str:
    """SQL syntax highlighting"""
    # Keywords
    keywords = ['SELECT', 'FROM', 'WHERE', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER',
               'TABLE', 'INDEX', 'VIEW', 'DATABASE', 'SCHEMA', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER',
               'ON', 'GROUP', 'BY', 'ORDER', 'HAVING', 'UNION', 'DISTINCT', 'COUNT', 'SUM', 'AVG', 'MAX', 'MIN',
               'AND', 'OR', 'NOT', 'IN', 'BETWEEN', 'LIKE', 'IS', 'NULL', 'ASC', 'DESC', 'LIMIT', 'OFFSET']
    
    # String literals
    code = re.sub(r"('.*?')", r'<font color="#008000">\1</font>', code)
    
    # Comments
    code = re.sub(r'(--.*?)$', r'<font color="#808080">\1</font>', code, flags=re.MULTILINE)
    code = re.sub(r'(/\*[\s\S]*?\*/)', r'<font color="#808080">\1</font>', code)
    
    # Keywords (case insensitive)
    for keyword in keywords:
        code = re.sub(r'\b(' + keyword + r')\b', r'<font color="#0000FF"><b>\1</b></font>', code, flags=re.IGNORECASE)
    
    # Numbers
    code = re.sub(r'\b(\d+\.?\d*)\b', r'<font color="#FF0000">\1</font>', code)
    
    return f"<font name='Courier' size='9'>{code}</font>"


def _highlight_yaml(code: str) -> str:
    """YAML syntax highlighting"""
    # Keys
    code = re.sub(r'^(\s*)([^:]+):', r'\1<font color="#0000FF"><b>\2</b></font>:', code, flags=re.MULTILINE)
    
    # String values
    code = re.sub(r'(".*?")', r'<font color="#008000">\1</font>', code)
    code = re.sub(r"('.*?')", r'<font color="#008000">\1</font>', code)
    
    # Numbers
    code = re.sub(r'\b(\d+\.?\d*)\b', r'<font color="#FF0000">\1</font>', code)
    
    # Booleans
    code = re.sub(r'\b(true|false|yes|no|on|off)\b', r'<font color="#800080"><b>\1</b></font>', code)
    
    # Comments
    code = re.sub(r'(#.*?)$', r'<font color="#808080">\1</font>', code, flags=re.MULTILINE)
    
    return f"<font name='Courier' size='9'>{code}</font>"


def _highlight_bash(code: str) -> str:
    """Bash/Shell syntax highlighting"""
    # Comments
    code = re.sub(r'(#.*?)$', r'<font color="#808080">\1</font>', code, flags=re.MULTILINE)
    
    # Commands (first word on line)
    code = re.sub(r'^(\s*)([a-zA-Z_][a-zA-Z0-9_]*)', r'\1<font color="#0000FF"><b>\2</b></font>', code, flags=re.MULTILINE)
    
    # Variables
    code = re.sub(r'(\$[a-zA-Z_][a-zA-Z0-9_]*)', r'<font color="#800080">\1</font>', code)
    code = re.sub(r'(\$\{[^}]+\})', r'<font color="#800080">\1</font>', code)
    
    # Strings
    code = re.sub(r'(".*?")', r'<font color="#008000">\1</font>', code)
    code = re.sub(r"('.*?')", r'<font color="#008000">\1</font>', code)
    
    # Redirections and pipes
    code = re.sub(r'([<>|&])', r'<font color="#FF0000"><b>\1</b></font>', code)
    
    return f"<font name='Courier' size='9'>{code}</font>"


def _format_inline_markdown(text: str) -> str:
    """
    Format inline markdown elements (bold, italic, code, links)
    """
    # Escape HTML characters first
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    
    # Process in order of precedence to avoid nested tag conflicts
    # 1. Inline code (`code`) - highest precedence, no nested formatting
    text = re.sub(r'`([^`]+)`', r'<font name="Courier" size="9">\1</font>', text)
    
    # 2. Bold text (**text** or __text__) - but not inside code blocks
    text = re.sub(r'(?<!`)\*\*([^*]+)\*\*(?!`)', r'<b>\1</b>', text)
    text = re.sub(r'(?<!`)__(?!_)([^_]+)__(?!`)', r'<b>\1</b>', text)
    
    # 3. Italic text (*text* or _text_) - but not inside code blocks or bold
    text = re.sub(r'(?<!`)(?<!\*)\*([^*]+)\*(?!\*)(?!`)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!`)(?<!_)_([^_]+)_(?!_)(?!`)', r'<i>\1</i>', text)
    
    # 4. Strikethrough (~~text~~) - but not inside other formatting
    text = re.sub(r'~~([^~]+)~~', r'<strike>\1</strike>', text)
    
    # 5. Links [text](url) - convert to clickable text
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<link href="\2">\1</link>', text)
    
    # 6. Line breaks
    text = text.replace('\n', '<br/>')
    
    return text


def _apply_syntax_highlight(escaped_code: str, language: str) -> str:
    """
    Apply professional IDE-like syntax highlighting on XML-escaped code text.
    Works with escaped entities (&lt; &gt; &amp;), so regexes should not rely on raw quotes.
    """
    def sub_outside_tags(pattern, repl, text, flags=0):
        parts = re.split(r'(</?[^>]+>)', text)
        for idx in range(0, len(parts)):
            if idx % 2 == 0:  # outside tags
                parts[idx] = re.sub(pattern, repl, parts[idx], flags=flags)
        return ''.join(parts)

    out = escaped_code
    lang = (language or 'text').lower()

    if lang in ('python', 'py'):
        # Comments first (gray)
        out = sub_outside_tags(r"(#[^\n]*)", r"<font color='#6a737d'>\1</font>", out)
        # Docstrings (green)
        out = sub_outside_tags(r'(&quot;&quot;&quot;[\s\S]*?&quot;&quot;&quot;)', r"<font color='#28a745'>\1</font>", out)
        out = sub_outside_tags(r"(&#x27;&#x27;&#x27;[\s\S]*?&#x27;&#x27;&#x27;)", r"<font color='#28a745'>\1</font>", out)
        # Keywords (purple)
        keywords = (
            'def|class|if|else|elif|for|while|try|except|finally|import|from|as|with|return|yield|lambda|and|or|not|in|is|True|False|None|pass|break|continue|raise|assert|global|nonlocal'
        )
        out = sub_outside_tags(rf"\b({keywords})\b", r"<font color='#6f42c1'><b>\1</b></font>", out)
        # Built-in functions (blue)
        builtins = (
            'print|len|str|int|float|list|dict|tuple|set|range|enumerate|zip|map|filter|sorted|reversed|open|input|type|isinstance|hasattr|getattr|setattr|delattr'
        )
        out = sub_outside_tags(rf"\b({builtins})\b", r"<font color='#005cc5'>\1</font>", out)

    elif lang in ('javascript', 'js', 'typescript', 'ts'):
        # Comments (gray)
        out = sub_outside_tags(r"(//[^\n]*)", r"<font color='#6a737d'>\1</font>", out)
        out = sub_outside_tags(r"/\*[\s\S]*?\*/", lambda m: f"<font color='#6a737d'>{m.group(0)}</font>", out)
        # Keywords (purple)
        keywords = (
            'function|var|let|const|if|else|for|while|do|switch|case|break|continue|return|try|catch|finally|throw|new|this|typeof|instanceof|true|false|null|undefined|async|await|class|extends|implements|interface|type|namespace|module|export|import|default|public|private|protected|static|abstract|readonly'
        )
        out = sub_outside_tags(rf"\b({keywords})\b", r"<font color='#6f42c1'><b>\1</b></font>", out)
        # Built-in objects (blue)
        builtins = (
            'console|window|document|Array|Object|String|Number|Boolean|Date|Math|JSON|Promise|Set|Map|WeakSet|WeakMap|Symbol|Proxy|Reflect'
        )
        out = sub_outside_tags(rf"\b({builtins})\b", r"<font color='#005cc5'>\1</font>", out)

    elif lang in ('json',):
        # Boolean and null values (blue)
        out = sub_outside_tags(r"\b(true|false|null)\b", r"<font color='#005cc5'><b>\1</b></font>", out)
        # Keys (purple)
        out = sub_outside_tags(r"(&quot;[^&]*?&quot;)(\s*:)", r"<font color='#6f42c1'>\1</font>\2", out)

    elif lang in ('bash', 'sh', 'shell'):
        # Comments (gray)
        out = sub_outside_tags(r"(#[^\n]*)", r"<font color='#6a737d'>\1</font>", out)
        # Commands (purple)
        out = sub_outside_tags(r"(^|\n)(\s*)([a-zA-Z_][a-zA-Z0-9_-]*)", r"\1\2<font color='#6f42c1'><b>\3</b></font>", out)
        # Variables (blue)
        out = sub_outside_tags(r"(\$[a-zA-Z_][a-zA-Z0-9_]*)", r"<font color='#005cc5'>\1</font>", out)
        out = sub_outside_tags(r"(\$\{[^}]+\})", r"<font color='#005cc5'>\1</font>", out)

    elif lang in ('yaml', 'yml'):
        # Keys (purple)
        out = sub_outside_tags(r"(^|\n)(\s*)([^:\n]+)(:)", r"\1\2<font color='#6f42c1'>\3</font>\4", out)
        # Boolean values (blue)
        out = sub_outside_tags(r"\b(true|false|yes|no|on|off)\b", r"<font color='#005cc5'><b>\1</b></font>", out, flags=re.IGNORECASE)

    elif lang in ('sql',):
        # Keywords (purple)
        keywords = (
            'SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TABLE|INDEX|VIEW|DATABASE|SCHEMA|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|HAVING|UNION|DISTINCT|COUNT|SUM|AVG|MAX|MIN|AND|OR|NOT|IN|BETWEEN|LIKE|IS|NULL|ASC|DESC|LIMIT|OFFSET|CASE|WHEN|THEN|ELSE|END|EXISTS|ALL|ANY|SOME'
        )
        out = sub_outside_tags(rf"\b({keywords})\b", r"<font color='#6f42c1'><b>\1</b></font>", out, flags=re.IGNORECASE)

    elif lang in ('java',):
        # Comments (gray)
        out = sub_outside_tags(r"(//[^\n]*)", r"<font color='#6a737d'>\1</font>", out)
        out = sub_outside_tags(r"/\*[\s\S]*?\*/", lambda m: f"<font color='#6a737d'>{m.group(0)}</font>", out)
        # Keywords (purple)
        keywords = (
            'public|private|protected|static|final|class|interface|extends|implements|if|else|for|while|do|switch|case|break|continue|return|try|catch|finally|throw|throws|new|this|super|import|package|void|int|long|float|double|boolean|char|byte|short|true|false|null|abstract|native|synchronized|volatile|transient|strictfp'
        )
        out = sub_outside_tags(rf"\b({keywords})\b", r"<font color='#6f42c1'><b>\1</b></font>", out)
        # Built-in classes (blue)
        builtins = (
            'String|Object|Integer|Long|Float|Double|Boolean|Character|Byte|Short|System|Math|ArrayList|HashMap|HashSet|LinkedList|Vector|Collections|Arrays'
        )
        out = sub_outside_tags(rf"\b({builtins})\b", r"<font color='#005cc5'>\1</font>", out)

    elif lang in ('css',):
        # Selectors (purple)
        out = sub_outside_tags(r"([.#]?[a-zA-Z][a-zA-Z0-9_-]*)(\s*\{)", r"<font color='#6f42c1'>\1</font>\2", out)
        # Properties (blue)
        out = sub_outside_tags(r"([a-zA-Z-]+)(\s*:)", r"<font color='#005cc5'>\1</font>\2", out)
        # Values (green)
        out = sub_outside_tags(r"(\s*:\s*)([^;]+)(;)", r"\1<font color='#28a745'>\2</font>\3", out)

    elif lang in ('html', 'xml'):
        # Tags (purple)
        out = sub_outside_tags(r"(&lt;[^&gt;]*&gt;)", r"<font color='#6f42c1'><b>\1</b></font>", out)
        # Attributes (blue)
        out = sub_outside_tags(r"(\w+)=(&quot;[^&]*?&quot;)", r"<font color='#005cc5'>\1</font>=\2", out)

    # Strings (green) - apply to all languages
    out = sub_outside_tags(r"(&quot;.*?&quot;)", r"<font color='#28a745'>\1</font>", out)
    out = sub_outside_tags(r"(&#x27;.*?&#x27;)", r"<font color='#28a745'>\1</font>", out)
    out = sub_outside_tags(r"(`.*?`)", r"<font color='#28a745'>\1</font>", out)

    # Numbers (orange) - apply to all languages
    out = sub_outside_tags(r"\b(\d+\.?\d*)\b", r"<font color='#e36209'>\1</font>", out)

    return out


def _render_mermaid_png(mermaid_text: str) -> bytes:
    """
    Render mermaid code to PNG via Kroki service (no local mermaid-cli dependency).
    Falls back to returning empty bytes on failure.
    """
    try:
        import base64
        import json
        import urllib.request
        import urllib.error
        
        # Validate and clean mermaid content
        if not mermaid_text or not mermaid_text.strip():
            logger.warning("[PDF] Empty mermaid content")
            return b""
        
        # Clean the mermaid text - remove any potential issues
        cleaned_text = mermaid_text.strip()
        
        # Basic mermaid syntax validation
        if not cleaned_text.startswith(('graph', 'flowchart', 'sequenceDiagram', 'classDiagram', 'stateDiagram', 'erDiagram', 'journey', 'gantt', 'pie', 'gitgraph')):
            logger.warning(f"[PDF] Invalid mermaid diagram type: {cleaned_text[:50]}...")
            return b""
        
        # Kroki POST API for mermaid -> png
        data = json.dumps({"diagram_source": cleaned_text}).encode("utf-8")
        req = urllib.request.Request(
            url="https://kroki.io/mermaid/png",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return resp.read()
            else:
                logger.warning(f"[PDF] Kroki returned status {resp.status}")
                return b""
                
    except urllib.error.HTTPError as e:
        if e.code == 400:
            logger.warning(f"[PDF] Kroki mermaid syntax error (400): {e.reason}")
        else:
            logger.warning(f"[PDF] Kroki HTTP error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        logger.warning(f"[PDF] Kroki connection error: {e.reason}")
    except Exception as e:
        logger.warning(f"[PDF] Kroki mermaid render error: {e}")
    
    return b""


async def _format_references_ieee(sources: List[Dict]) -> List[str]:
    """Format sources in IEEE citation style using NVIDIA API."""
    try:
        from utils.api.router import generate_answer_with_model
        from helpers.setup import nvidia_rotator
        
        if not sources or not nvidia_rotator:
            return []
        
        # Prepare source data for formatting
        source_data = []
        for i, source in enumerate(sources, 1):
            source_info = {
                "number": i,
                "filename": source.get("filename", "Unknown"),
                "url": source.get("url", ""),
                "topic_name": source.get("topic_name", ""),
                "kind": source.get("kind", "document")
            }
            source_data.append(source_info)
        
        sys_prompt = """You are an expert at formatting academic references in IEEE style.
Format the provided sources as IEEE-style references. Each reference should be numbered and formatted according to IEEE standards.

For web sources: [1] Author/Organization, "Title," Website Name, URL, accessed: Date.
For documents: [1] Author, "Title," Document Type, Filename, Year.

Return only the formatted references, one per line, numbered sequentially."""
        
        user_prompt = f"Format these sources in IEEE style:\n\n{source_data}"
        
        selection = {"provider": "nvidia", "model": "meta/llama-3.1-8b-instruct"}
        response = await generate_answer_with_model(selection, sys_prompt, user_prompt, None, nvidia_rotator, user_id="system", context="pdf_citation")
        
        # Parse the response into individual references
        references = [line.strip() for line in response.split('\n') if line.strip() and line.strip().startswith('[')]
        
        # If NVIDIA formatting fails, create basic IEEE format
        if not references:
            references = []
            for i, source in enumerate(sources, 1):
                if source.get("kind") == "web":
                    ref = f"[{i}] {source.get('topic_name', 'Unknown')}, \"{source.get('filename', 'Web Source')}\", {source.get('url', '')}, accessed: {datetime.now().strftime('%B %d, %Y')}."
                else:
                    ref = f"[{i}] {source.get('topic_name', 'Unknown')}, \"{source.get('filename', 'Document')}\", Document, {datetime.now().year}."
                references.append(ref)
        
        return references
        
    except Exception as e:
        logger.warning(f"[PDF] IEEE reference formatting failed: {e}")
        # Fallback to basic formatting
        references = []
        for i, source in enumerate(sources, 1):
            if source.get("kind") == "web":
                ref = f"[{i}] {source.get('topic_name', 'Unknown')}, \"{source.get('filename', 'Web Source')}\", {source.get('url', '')}, accessed: {datetime.now().strftime('%B %d, %Y')}."
            else:
                ref = f"[{i}] {source.get('topic_name', 'Unknown')}, \"{source.get('filename', 'Document')}\", Document, {datetime.now().year}."
            references.append(ref)
        return references


async def generate_report_pdf(report_content: str, user_id: str, project_id: str, sources: List[Dict] = None) -> bytes:
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
        
        # Professional IDE-like code styling with no background
        base_code_parent = styles['Code'] if 'Code' in styles.byName else styles['Normal']
        code_style = ParagraphStyle(
            'Code',
            parent=base_code_parent,
            fontSize=9,
            fontName='Courier',
            textColor=colors.HexColor('#2c3e50'),  # Dark text on white background
            backColor=None,  # No background color
            borderColor=colors.HexColor('#e1e8ed'),
            borderWidth=1,
            borderPadding=8,
            leftIndent=12,
            rightIndent=12,
            spaceBefore=6,
            spaceAfter=6,
            leading=11
        )
        
        # Parse markdown content
        story = []
        
        # Add title
        story.append(Paragraph("StudyBuddy Report", title_style))
        story.append(Paragraph(f"<i>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</i>", normal_style))
        story.append(Spacer(1, 20))
        
        # Enhanced markdown parser with proper formatting
        story.extend(await _parse_markdown_content(report_content, heading1_style, heading2_style, heading3_style, normal_style, code_style))
        
        # Add references section if sources provided
        if sources:
            story.append(PageBreak())
            story.append(Paragraph("References", heading1_style))
            story.append(Spacer(1, 12))
            
            # Format references in IEEE style using NVIDIA API
            try:
                ieee_references = await _format_references_ieee(sources)
            except Exception as _ie:
                logger.warning(f"[PDF] Reference formatting failed, falling back: {_ie}")
                ieee_references = []
                for i, source in enumerate(sources, 1):
                    if source.get("kind") == "web":
                        ref = f"[{i}] {source.get('topic_name', 'Unknown')}, \"{source.get('filename', 'Web Source')}\", {source.get('url', '')}, accessed: {datetime.now().strftime('%B %d, %Y')}."
                    else:
                        ref = f"[{i}] {source.get('topic_name', 'Unknown')}, \"{source.get('filename', 'Document')}\", Document, {datetime.now().year}."
                    ieee_references.append(ref)
            for ref in ieee_references:
                story.append(Paragraph(ref, normal_style))
                story.append(Spacer(1, 6))
        
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
        # Keep error generic for client; avoid leaking internals
        raise HTTPException(500, detail="Failed to generate PDF")
