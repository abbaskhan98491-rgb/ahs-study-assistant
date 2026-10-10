"""Extract unit/topic/learning-outcome rows from the supplied KMU PDF.

Usage: python import_syllabus.py PATH_TO_PDF
Only the four requested subjects are imported. Document prose is data.
"""
import json
import re
import sys
from pathlib import Path
import pymupdf


def clean(value):
    value = (value or '').replace('\xad\n', '').replace('\xad', '')
    return re.sub(r'\s+', ' ', value).strip()


def extract(path):
    subjects = {}
    counts = {}
    ranges = {'Biochemistry': range(11, 15), 'Physiology': range(16, 24),
              'Anatomy': range(25, 32), 'English': range(33, 36)}
    with pymupdf.open(path) as doc:
        for subject, pages in ranges.items():
            units = subjects[subject] = {}
            unit = topic = None
            counts[subject] = {'cognitive': 0, 'practical': 0, 'affective': 0}
            for page_index in pages:
                tables = doc[page_index].find_tables().tables
                assert len(tables) == 1, f'Check table on PDF page {page_index + 1}'
                table_rows = tables[0].extract()
                # Some pages have extra empty columns; use domain labels, not fixed offsets.
                domain_columns = {clean(value): index for index, value in enumerate(table_rows[1])
                                  if clean(value) in ('C', 'P', 'A')}
                assert len(domain_columns) == 3, page_index + 1
                for row in table_rows:
                    if row[0] and 'TOPIC:' in row[0]:
                        unit = clean(row[0].split('TOPIC:', 1)[1]).title()
                        units.setdefault(unit, {})
                        topic = None
                        continue
                    if not clean(row[0]).isdigit():
                        continue
                    content, outcome = clean(row[2]), clean(row[3])
                    cognitive = clean(row[domain_columns['C']])
                    practical = clean(row[domain_columns['P']])
                    affective = clean(row[domain_columns['A']])
                    # These cells are blank in the supplied PDF. Classification follows
                    # the surrounding theory rows, or the explicit Demo row for row 44.
                    inferred = False
                    if subject == 'Physiology' and page_index + 1 == 18 and clean(row[0]) == '44':
                        practical, inferred = 'P', True
                    if subject == 'Physiology' and page_index + 1 == 21 and 97 <= int(row[0]) <= 104:
                        cognitive, inferred = 'C', True
                    if re.fullmatch(r'C\d*', cognitive):
                        if content and not content.lower().startswith('practical'):
                            # English content cells are long summaries of the unit.
                            topic = unit if subject == 'English' else content
                        assert unit and topic and outcome, (subject, page_index + 1, row)
                        units[unit].setdefault(topic, []).append(
                            {'text': outcome, 'pdf_page': page_index + 1, 'row': clean(row[0]),
                             'domain_inferred': inferred})
                        counts[subject]['cognitive'] += 1
                    elif re.fullmatch(r'P\d*', practical):
                        assert outcome
                        units.setdefault('Practical / OSPE', {}).setdefault(outcome, []).append(
                            {'text': outcome, 'pdf_page': page_index + 1, 'row': clean(row[0]),
                             'domain_inferred': inferred})
                        counts[subject]['practical'] += 1
                    elif re.fullmatch(r'A\d*', affective):
                        counts[subject]['affective'] += 1
                    else:
                        raise ValueError(f'Unclassified row: {subject} PDF page {page_index + 1}: {row}')
    return {'source': Path(path).name, 'edition': 'KMU 2021-22 semester 2',
            'row_counts': counts, 'subjects': subjects}


if __name__ == '__main__':
    data = extract(sys.argv[1])
    Path('syllabus_details.json').write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                           encoding='utf-8')
    print(json.dumps(data['row_counts'], indent=2))
