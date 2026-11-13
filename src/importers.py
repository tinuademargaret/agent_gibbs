from pathlib import Path
import pymupdf
from src.qa_parser import parse
MAX_BYTES = 20 * 1024 * 1024

def extract(data: bytes, filename: str):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Choose a nonempty file no larger than 20 MB.')
    suffix = Path(filename).suffix.lower()
    pages = None
    warnings = []
    if suffix == '.pdf':
        try:
            with pymupdf.open(stream=data, filetype='pdf') as document:
                if document.needs_pass:
                    raise ValueError('This PDF is password protected. Upload an unlocked copy.')
                if len(document) > 500:
                    raise ValueError('PDFs are limited to 500 pages per import.')
                lines, pages = [], []
                empty = 0
                for number, page in enumerate(document, 1):
                    text = page.get_text(sort=True)
                    if len(text.strip()) < 20:
                        empty += 1
                    chunk = text.splitlines()
                    lines.extend(chunk)
                    pages.extend([number] * len(chunk))
                text = '\n'.join(lines)
                if empty:
                    warnings.append('This PDF may be scanned: some pages have little or no extractable text. OCR is not included.')
        except (pymupdf.FileDataError, RuntimeError) as exc:
            raise ValueError('This PDF could not be read. Try an unlocked text-based PDF.') from exc
    elif suffix in ('.txt', '.md'):
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('Save the text file as UTF-8 and try again.') from exc
    else:
        raise ValueError('Supported file types: PDF, TXT, MD.')
    result = parse(text, filename, pages)
    result.warnings.extend(warnings)
    return text, result
