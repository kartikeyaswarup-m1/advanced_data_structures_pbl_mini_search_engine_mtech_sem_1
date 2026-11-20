"""Load the editable text corpus and expand it for performance experiments."""
from pathlib import Path

DOCUMENTS_DIR = Path(__file__).resolve().parent / 'documents'


def load_documents(directory: Path = DOCUMENTS_DIR) -> list[dict]:
    """Read UTF-8 files with ID/Title headers, a blank line, then body text.

    Only body text is indexed. IDs determine order independently of filenames.
    Invalid or duplicate metadata fails explicitly rather than losing documents.
    """
    paths = sorted(Path(directory).glob('*.txt'))
    if not paths:
        raise ValueError(f'No .txt documents found in {directory}')
    documents = []
    seen = set()
    for path in paths:
        lines = path.read_text(encoding='utf-8').splitlines()
        if (len(lines) < 4 or not lines[0].startswith('ID: ')
                or not lines[1].startswith('Title: ') or lines[2].strip()):
            raise ValueError(f'{path.name}: expected ID, Title, blank line, and body')
        try:
            doc_id = int(lines[0][4:])
        except ValueError as exc:
            raise ValueError(f'{path.name}: ID must be a positive integer') from exc
        title = lines[1][7:].strip()
        text = '\n'.join(lines[3:]).strip()
        if doc_id <= 0 or doc_id in seen or not title or not text:
            raise ValueError(f'{path.name}: positive unique ID, title, and body are required')
        seen.add(doc_id)
        documents.append({'id': doc_id, 'title': title, 'text': text})
    return sorted(documents, key=lambda doc: doc['id'])


def benchmark_documents(n: int) -> list[dict]:
    """Use the actual files; repeat paragraph topics for larger synthetic sets."""
    base = load_documents()
    if len(base) != 20:
        raise ValueError('Performance experiments require exactly 20 initial documents')
    if n not in (10, 20, 25, 50, 100):
        raise ValueError('supported corpus sizes: 10, 20, 25, 50, 100')
    documents = [doc.copy() for doc in base[:n]]
    next_id = max(doc['id'] for doc in base) + 1
    for offset in range(max(0, n - len(base))):
        source = base[offset % len(base)]
        documents.append({
            'id': next_id + offset,
            'title': f'Research Note {next_id + offset:03d}: {source["title"]}',
            'text': source['text'] + '\nThis extended example supports repeated performance measurements with a larger collection.',
        })
    return documents
