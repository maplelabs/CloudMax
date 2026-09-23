"""
Confluence XHTML to Markdown conversion
"""
import html
import logging
import re

from bs4 import BeautifulSoup
from markdownify import markdownify

logger = logging.getLogger(__name__)


INFO_MACRO_TYPES = {'info', 'note', 'tip', 'warning'}
DEFAULT_MACRO_TITLES = {
    'info': 'Info',
    'note': 'Info',
    'tip': 'Info',
    'warning': 'Warning'
}


def _get_macro_title(macro, macro_name: str) -> str:
    """Extract title from macro or use default."""
    title_element = macro.find('ac:parameter', {'ac:name': 'title'})
    if title_element:
        return title_element.get_text(strip=True)
    return DEFAULT_MACRO_TITLES.get(macro_name, 'Info')


def _get_macro_body(macro) -> str:
    """Extract body text from macro."""
    body = macro.find('ac:rich-text-body')
    return body.get_text(strip=True) if body else ''


def _sanitize_macro_content(content: str) -> str:
    """
    Sanitize macro content to prevent HTML/markdown injection.

    Escapes HTML entities and markdown special characters that could be abused.
    """
    # Escape HTML entities
    content = html.escape(content, quote=False)
    # Escape markdown special characters that could cause issues
    # Don't escape * and _ as they're commonly used in content
    content = content.replace('[', '\\[').replace(']', '\\]')
    return content


def _convert_info_macro_to_blockquote(macro, macro_name: str) -> str:
    """Convert info/warning/note/tip macros to blockquotes with sanitized content."""
    title_text = _sanitize_macro_content(_get_macro_title(macro, macro_name))
    body_text = _sanitize_macro_content(_get_macro_body(macro))
    return f"\n\n> **{title_text}**\n> {body_text}\n\n"


def _get_code_language(macro) -> str:
    """Extract language from code macro."""
    language = macro.find('ac:parameter', {'ac:name': 'language'})
    return language.get_text(strip=True) if language else ''


def _get_code_content(macro) -> str:
    """Extract code content from macro."""
    code_body = macro.find('ac:plain-text-body')
    if code_body and code_body.string:
        return code_body.string.strip()
    return macro.get_text(strip=True)


def _convert_code_macro_to_markdown(macro) -> str:
    """Convert code macros to markdown code blocks."""
    lang = _get_code_language(macro)
    code_text = _get_code_content(macro)
    return f"\n\n```{lang}\n{code_text}\n```\n\n"


def _convert_unknown_macro(macro, macro_name: str) -> str:
    """Convert unknown macros to text markers."""
    macro_body = macro.get_text(strip=True)
    return f"\n\n[{macro_name.upper()}]\n{macro_body}\n\n"


def _convert_macro_to_markdown(macro) -> str:
    """Convert a single Confluence macro to markdown."""
    macro_name = macro.get('ac:name', 'unknown')

    if macro_name in INFO_MACRO_TYPES:
        return _convert_info_macro_to_blockquote(macro, macro_name)

    if macro_name == 'code':
        return _convert_code_macro_to_markdown(macro)

    return _convert_unknown_macro(macro, macro_name)


def replace_confluence_macros(soup: BeautifulSoup) -> None:
    """
    Replace Confluence macros with appropriate markdown equivalents.

    Handles:
    - info/warning/note macros → Blockquotes
    - code macros → Code blocks with language
    - Other macros → Text markers

    Args:
        soup: BeautifulSoup object (modified in-place)
    """
    for macro in soup.find_all('ac:structured-macro'):
        replacement = _convert_macro_to_markdown(macro)
        macro.replace_with(replacement)


def _clean_markdown(markdown: str) -> str:
    """Clean up markdown formatting."""
    markdown = _fix_table_formatting(markdown)
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    return markdown.strip()


async def convert_to_markdown(content: str) -> str:
    """
    Convert Confluence storage format (XHTML) to markdown.

    Known Limitations:
    - Macros converted to text markers or blockquotes
    - Images kept as authenticated URLs
    - Complex tables may lose structure

    Args:
        content: Confluence XHTML storage content

    Returns:
        Markdown formatted string
    """
    if not content:
        logger.warning("[CONFLUENCE] Empty content passed to convert_to_markdown")
        return ""

    logger.warning(f"[CONFLUENCE] Converting {len(content)} chars XHTML to markdown")

    try:
        soup = BeautifulSoup(content, 'html.parser')
        replace_confluence_macros(soup)
        markdown = _convert_soup_to_markdown(soup)
        result = _clean_markdown(markdown)
        logger.warning(f"[CONFLUENCE] Converted to {len(result)} chars markdown")
        return result
    except Exception as e:
        logger.error(f"[CONFLUENCE] Failed to convert XHTML to markdown: {e}", exc_info=True)
        logger.error(f"[CONFLUENCE] Content preview: {content[:500]}")
        raise


def _convert_soup_to_markdown(soup: BeautifulSoup) -> str:
    """Convert BeautifulSoup to markdown using markdownify."""
    return markdownify(
        str(soup),
        heading_style="ATX",
        bullets="-",
        strip=['script', 'style'],
        newline_style="BACKSLASH"
    )


def _fix_table_formatting(markdown: str) -> str:
    """Fix table formatting issues from markdownify."""
    # Add spaces around pipe characters if not already present
    markdown = re.sub(r'\|(?!\s)', '| ', markdown)
    markdown = re.sub(r'(?<!\s)\|', ' |', markdown)

    # Ensure proper line breaks in tables (don't modify existing line breaks)
    # This just ensures tables end with newlines for proper formatting
    return markdown
