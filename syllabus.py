"""
BS Allied Health Sciences - 2nd Semester Syllabus
Topics organized by subject, taken from the supplied KMU 2021-22 curriculum
(PMS-607/608/609/610). Islamic Studies is excluded by the user's preference.
Source PDF pages: Biochemistry 12-15, Physiology 17-24, Anatomy 26-32,
English 34-36. This is a topic outline, not a source of textbook answers.
Used by app.py to build the dropdown menus.
"""
import json
from pathlib import Path

SYLLABUS_DATA = json.loads(Path(__file__).with_name('syllabus_details.json').read_text(encoding='utf-8'))
SYLLABUS_DETAILS = SYLLABUS_DATA['subjects']


def build_study_scope(subject, unit, topic=None, subtopic=None):
    """Turn syllabus selections into explicit coverage and balanced search terms."""
    topics = SYLLABUS_DETAILS[subject][unit]
    selected = {topic: topics[topic]} if topic else topics
    sections, searches = [], []
    for name, outcomes in selected.items():
        rows = [row for row in outcomes if not subtopic or row['text'] == subtopic]
        if not rows:
            raise ValueError('Subtopic does not belong to selected topic')
        sections.append(name + ':\n' + '\n'.join('- ' + row['text'] for row in rows))
        # Whole-unit retrieval balances topics; single-topic retrieval covers its aspects.
        if topic:
            searches.extend(f'{subject} {unit}: {name}: {row["text"]}' for row in rows)
        else:
            searches.append(f'{subject} {unit}: {name}: ' + '; '.join(row['text'] for row in rows)[:250])
    title = f'{subject} / {unit}' + (f' / {topic}' if topic else ' / Whole unit')
    if subtopic:
        title += f' / {subtopic}'
    request = title + '\nSyllabus coverage:\n' + '\n\n'.join(sections)
    request += ('\nCover these items using the selected source only. For study, use separate '
                'headings. For MCQs, distribute questions across the listed items. '
                'Clearly identify items not supported by the retrieved source; never invent coverage.')
    return request, tuple(dict.fromkeys(searches))
