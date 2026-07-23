import io
import re
import logging
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)

def flatten_at_layers(css_content: str) -> str:
    """
    Flattens `@layer <name> { ... }` wrappers by lifting nested CSS rules to the top level.
    """
    cleaned_css = css_content
    pattern = re.compile(r'@layer\s+[a-zA-Z0-9_-]+\s*\{')
    
    while True:
        match = pattern.search(cleaned_css)
        if not match:
            break
            
        start_idx = match.start()
        brace_start = cleaned_css.find('{', start_idx)
        if brace_start == -1:
            break
            
        brace_count = 1
        current_idx = brace_start + 1
        n = len(cleaned_css)
        while current_idx < n and brace_count > 0:
            char = cleaned_css[current_idx]
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            current_idx += 1
            
        if brace_count == 0:
            closing_brace_idx = current_idx - 1
            inner_content = cleaned_css[brace_start + 1:closing_brace_idx]
            cleaned_css = cleaned_css[:start_idx] + inner_content + cleaned_css[closing_brace_idx + 1:]
        else:
            cleaned_css = cleaned_css[:start_idx] + cleaned_css[brace_start + 1:]
            
    return cleaned_css

def strip_unsupported_css_rules(css_content: str) -> str:
    """
    Strip CSS rules containing pseudo-classes or functions unsupported by xhtml2pdf,
    such as :where(), :is(), :has(), and ::backdrop.
    Also strips any individual property declarations that use unsupported CSS functions
    like calc(), var(), oklch(), and relative rgb/rgba colors.
    """
    cleaned_css = css_content
    new_css = []
    idx = 0
    n = len(cleaned_css)
    while idx < n:
        brace_start = cleaned_css.find('{', idx)
        if brace_start == -1:
            new_css.append(cleaned_css[idx:])
            break
            
        selector_start = idx
        last_boundary = max(cleaned_css.rfind('}', idx, brace_start), cleaned_css.rfind(';', idx, brace_start))
        if last_boundary != -1:
            selector_start = last_boundary + 1
            
        selector = cleaned_css[selector_start:brace_start].strip()
        
        brace_count = 1
        current_idx = brace_start + 1
        while current_idx < n and brace_count > 0:
            char = cleaned_css[current_idx]
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            current_idx += 1
            
        if brace_count == 0:
            closing_brace_idx = current_idx - 1
            
            unsupported = [":where", ":is", ":has", ":not", "::backdrop", "::placeholder", "::file-selector-button", "::selection", ":-moz-", ":-webkit-"]
            is_unsupported = any(feat in selector for feat in unsupported)
            
            if not is_unsupported:
                # Sanitize declarations inside the rule
                props_block = cleaned_css[brace_start + 1:closing_brace_idx]
                cleaned_props = []
                for prop in props_block.split(';'):
                    prop = prop.strip()
                    if not prop:
                        continue
                    # Skip properties with calc, var, oklch, or rgb/rgba relative syntax
                    unsupported_vals = ["calc(", "var(", "oklch(", "rgb(from", "rgba(from"]
                    if any(val in prop for val in unsupported_vals):
                        continue
                    cleaned_props.append(prop)
                
                cleaned_rule_body = "; ".join(cleaned_props)
                if cleaned_rule_body:
                    cleaned_rule_body = " " + cleaned_rule_body + "; "
                new_css.append(cleaned_css[idx:brace_start + 1] + cleaned_rule_body + "}")
            else:
                new_css.append(cleaned_css[idx:selector_start])
                
            idx = closing_brace_idx + 1
        else:
            new_css.append(cleaned_css[idx:])
            break
            
    return "".join(new_css)

def strip_unsupported_at_rules(css_content: str) -> str:
    """
    Remove all CSS at-rules starting with '@' (except @page and @font-face)
    and their blocks/statements, to prevent xhtml2pdf crashes on modern CSS.
    """
    cleaned_css = css_content
    idx = 0
    while True:
        idx = cleaned_css.find('@', idx)
        if idx == -1:
            break
            
        match = re.match(r'^@([a-zA-Z0-9_-]+)', cleaned_css[idx:])
        if not match:
            idx += 1
            continue
            
        rule_name = match.group(1).lower()
        if rule_name in ["page", "font-face"]:
            idx += len(rule_name) + 1
            continue
            
        prefix_len = len(rule_name) + 1
        search_start = idx + prefix_len
        
        brace_idx = cleaned_css.find('{', search_start)
        semi_idx = cleaned_css.find(';', search_start)
        
        is_block = False
        if brace_idx != -1:
            if semi_idx == -1 or brace_idx < semi_idx:
                is_block = True
                
        if is_block:
            brace_count = 1
            current_idx = brace_idx + 1
            n = len(cleaned_css)
            while current_idx < n and brace_count > 0:
                char = cleaned_css[current_idx]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                current_idx += 1
                
            if brace_count == 0:
                cleaned_css = cleaned_css[:idx] + cleaned_css[current_idx:]
            else:
                cleaned_css = cleaned_css[:idx]
        else:
            if semi_idx != -1:
                cleaned_css = cleaned_css[:idx] + cleaned_css[semi_idx + 1:]
            else:
                cleaned_css = cleaned_css[:idx]
                
    return cleaned_css

def clean_html_css(html_content: str) -> str:
    """
    Cleans style tags by:
    1. Auto-closing unclosed style tags.
    2. Removing incomplete trailing rules due to truncation.
    3. Flattening @layer definitions.
    4. Stripping unsupported at-rules (@supports, @theme, @utility, etc.).
    5. Stripping unsupported selectors (:where, :is, :has, etc.) and values (calc, var, oklch).
    """
    # Auto-close style tag if open but not closed (due to truncation)
    if "<style" in html_content.lower() and "</style>" not in html_content.lower():
        html_content += "</style></head><body></body></html>"
        
    style_pattern = re.compile(r'(<style[^>]*>)(.*?)(</style>)', re.DOTALL | re.IGNORECASE)
    
    def clean_style_block(match):
        open_tag = match.group(1)
        css_content = match.group(2)
        close_tag = match.group(3)
        
        # Discard trailing incomplete rule due to truncation
        last_brace = css_content.rfind('}')
        if last_brace != -1:
            css_content = css_content[:last_brace + 1]
            
        # 1. Flatten nested @layer blocks
        css_content = flatten_at_layers(css_content)
        # 2. Strip unsupported at-rules (like @import, @supports, @utility, @theme, etc.)
        css_content = strip_unsupported_at_rules(css_content)
        # 3. Strip unsupported CSS rules (like :where, :is, :has) and values
        css_content = strip_unsupported_css_rules(css_content)
        
        return f"{open_tag}{css_content}{close_tag}"

    # Strip external stylesheets to bypass ReportLab urlopen Windows path bug
    cleaned_html = re.sub(r'<link[^>]*>', '', html_content, flags=re.IGNORECASE)
    
    return style_pattern.sub(clean_style_block, cleaned_html)

class PDFService:
    def convert_html_to_pdf(self, html_content: str) -> bytes:
        """
        Converts an HTML string into PDF binary data using xhtml2pdf.
        Automatically cleans CSS style tags and flattens Tailwind layers.
        """
        cleaned_html = clean_html_css(html_content)
        pdf_buffer = io.BytesIO()
        try:
            pisa_status = pisa.CreatePDF(
                src=cleaned_html,
                dest=pdf_buffer
            )
            if pisa_status.err:
                logger.error("xhtml2pdf error during conversion: %s", pisa_status.err)
                raise Exception(f"Failed to convert HTML to PDF: {pisa_status.err} errors encountered")
            
            return pdf_buffer.getvalue()
        except Exception as e:
            import traceback
            logger.error("Error generating PDF from HTML: %s", str(e), exc_info=True)
            try:
                import tempfile
                import os
                temp_path = os.path.join(tempfile.gettempdir(), "pdf_crash_debug.txt")
                with open(temp_path, "w", encoding="utf-8") as debug_f:
                    debug_f.write("=== ERROR ===\n")
                    debug_f.write(str(e) + "\n\n")
                    debug_f.write("=== TRACEBACK ===\n")
                    traceback.print_exc(file=debug_f)
                    debug_f.write("\n=== CLEANED HTML ===\n")
                    debug_f.write(cleaned_html)
                logger.error("Saved PDF crash debug info to %s", temp_path)
            except Exception as debug_err:
                logger.error("Failed to write pdf_crash_debug.txt: %s", debug_err)
            raise e

pdf_service = PDFService()
