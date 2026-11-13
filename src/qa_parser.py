"""Deterministic label parser. Text inside code fences is never interpreted as labels."""
import re
from dataclasses import dataclass, field

@dataclass
class Draft:
    question: str = ''
    short_answer: str = ''
    detailed_explanation: str = ''
    source_name: str = 'Pasted text'
    source_page: int | None = None
    source_excerpt: str = ''
    original_imported_answer: str = ''
    original_imported_explanation: str = ''
    tags: str = ''

@dataclass
class ParseResult:
    cards: list[Draft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

LABEL = re.compile(r'^\s*(?:[-*+]\s+)?(?:\*\*)?(Q(?:uestion)?|A(?:nswer)?|Detailed explanation|Explanation|Reasoning)(?:\*\*)?\s*:(?:\*\*)?[ \t]?(.*)$', re.I)
NUMBERED = re.compile(r'^\s*(?:#{1,6}\s+)?\d+[.)]\s+(.+)$')
HEADING = re.compile(r'^\s*#{1,6}\s+(.+\?)\s*$')

def parse(text: str, source_name='Pasted text', page_for_line=None) -> ParseResult:
    result = ParseResult()
    current = None
    fields = {}
    excerpt = []
    active = 'question'
    fence = None
    unmatched = []
    def finish():
        if current is not None:
            for name, lines in fields.items():
                setattr(current, name, '\n'.join(lines).strip('\n'))
            current.source_excerpt = '\n'.join(excerpt)
            current.original_imported_answer = current.short_answer
            current.original_imported_explanation = current.detailed_explanation
            result.cards.append(current)
    for index, line in enumerate(text.splitlines()):
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        match = LABEL.match(line) if fence is None else None
        numbered = (NUMBERED.match(line) or HEADING.match(line)) if fence is None and (current is None or active == 'question' or line.lstrip().startswith('#') or (excerpt and not excerpt[-1].strip() and line.rstrip().endswith('?'))) else None
        key = match.group(1).lower() if match else ''
        if (match and key in ('q', 'question')) or numbered:
            finish()
            current = Draft(source_name=source_name, source_page=page_for_line[index] if page_for_line else None)
            fields = {'question': [match.group(2) if match else numbered.group(1)], 'short_answer': [], 'detailed_explanation': []}
            excerpt = [line]
            active = 'question'
            continue
        if current is None:
            if line.strip():
                unmatched.append(line)
            continue
        excerpt.append(line)
        if match:
            active = 'short_answer' if key in ('a', 'answer') else 'detailed_explanation'
            if fields[active]:
                result.warnings.append('Repeated field label: check the source and preview for ambiguous boundaries.')
            fields[active].append(match.group(2))
        else:
            fields[active].append(line)
        if marker:
            char = marker.group(1)[0]
            fence = None if fence == char else char if fence is None else fence
    finish()
    if unmatched:
        result.warnings.append('Unmatched text was not converted. Use the source view to add or repair cards manually.')
    if any(not c.detailed_explanation.strip() for c in result.cards):
        result.warnings.append('Some cards need an explanation and will be saved as drafts.')
    if any(not c.short_answer.strip() for c in result.cards):
        result.warnings.append('Some cards need an answer and will be excluded from review.')
    if not result.cards:
        result.warnings.append('No question boundaries found. Add cards manually using the original source below.')
    return result
