"""Independent correctness and interactive regression tests (standard library)."""
import contextlib
import io
import itertools
import random
import re
import unittest
import tempfile
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from corpus import load_documents, benchmark_documents
from main import main
from search_engine import CompressedTrie, SearchEngine, StandardTrie, counts, intersect

ROOT = Path(__file__).parent


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = benchmark_documents(100)

    def test_text_corpus_metadata_and_paragraphs(self):
        docs = load_documents()
        self.assertEqual(len(list((ROOT / 'documents').glob('*.txt'))), 20)
        self.assertEqual([doc['id'] for doc in docs], list(range(1, 21)))
        self.assertEqual(len({doc['title'] for doc in docs}), 20)
        for doc in docs:
            self.assertGreaterEqual(len(doc['text'].split()), 25)
        self.assertEqual(self.docs[:20], docs)
        # The title is display metadata, rather than searchable body text.
        self.assertEqual(SearchEngine(docs).keyword_ids('fundamentals'), [])

    def test_loader_numeric_order_and_multiline_body(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.txt').write_text('ID: 12\nTitle: Later\n\nFirst line.\nSecond line.\n')
            (root / 'z.txt').write_text('ID: 3\nTitle: Earlier\n\nA separate body.\n')
            docs = load_documents(root)
            self.assertEqual([doc['id'] for doc in docs], [3, 12])
            self.assertEqual(docs[1]['text'], 'First line.\nSecond line.')
            (root / 'a.txt').write_text('ID: 12\nTitle: Edited\n\nUpdated body.\n')
            self.assertEqual(load_documents(root)[1]['text'], 'Updated body.')

    def test_loader_rejects_invalid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                load_documents(root)
            path = root / 'one.txt'
            invalid = [
                'Missing headers', 'ID: x\nTitle: Example\n\nBody',
                'ID: 0\nTitle: Example\n\nBody',
                'ID: 1\nTitle: \n\nBody',
                'ID: 1\nTitle: Example\n\n',
                'ID: 1\nTitle: Example\nBody without separator',
            ]
            for content in invalid:
                path.write_text(content)
                with self.subTest(content=content), self.assertRaises(ValueError):
                    load_documents(root)
            path.write_text('ID: 1\nTitle: First\n\nBody')
            (root / 'two.txt').write_text('ID: 1\nTitle: Second\n\nBody')
            with self.assertRaises(ValueError):
                load_documents(root)

    def test_cli_reads_text_files_without_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in ('main.py', 'corpus.py', 'search_engine.py'):
                shutil.copyfile(ROOT / filename, root / filename)
            (root / 'documents').mkdir()
            path = root / 'documents' / 'one.txt'
            path.write_text('ID: 42\nTitle: Local Document\n\nA uniqueedit example.')
            def run(query):
                return subprocess.run([sys.executable, '-B', str(root / 'main.py')],
                                      input=query + '\n\n', capture_output=True,
                                      text=True, check=True).stdout
            self.assertIn("(42, 'Local Document')", run('uniqueedit'))
            path.write_text('ID: 42\nTitle: Changed Title\n\nA replacement example.')
            self.assertIn('No matches', run('uniqueedit'))
            self.assertIn("(42, 'Changed Title')", run('replacement'))

    def test_all_corpora_against_document_scan(self):
        rng = random.Random(42)
        for n in (10, 20, 25, 50, 100):
            docs = self.docs[:n]
            engine = SearchEngine(docs)
            # Scan document tokens, without consulting either Trie or posting lists.
            tokens = {d['id']: set(re.findall(r'[a-z0-9]+', d['text'].lower())) for d in docs}
            for term in engine.terms:
                expected = sorted(i for i, words in tokens.items() if term in words)
                self.assertEqual(engine.keyword_ids(term.upper()), expected)
                self.assertEqual(engine.postings[engine.compressed.lookup(term)], expected)
            for _ in range(300):
                terms = rng.choices(engine.terms + ['unicorn'], k=rng.randint(1, 6))
                expected = sorted(i for i, words in tokens.items() if set(terms) <= words)
                self.assertEqual(engine.and_ids(' '.join(terms)), expected)

    def test_prefix_insertion_orders_and_overwrite(self):
        words = ['app', 'apple', 'application', 'apply', 'applied']
        for order in itertools.permutations(words):
            for cls in (StandardTrie, CompressedTrie):
                trie = cls()
                for i, word in enumerate(order):
                    trie.insert(word, i)
                for i, word in enumerate(order):
                    self.assertEqual(trie.lookup(word), i)
                for missing in ('', 'a', 'ap', 'appl', 'applications', 'banana'):
                    self.assertIsNone(trie.lookup(missing))
                before = counts(trie.root)
                trie.insert('app', 99)
                self.assertEqual(trie.lookup('app'), 99)
                self.assertEqual(counts(trie.root), before)

    def test_randomized_radix_invariants(self):
        rng = random.Random(7)
        for _ in range(50):
            terms = sorted(set(''.join(rng.choices('abcde', k=rng.randint(1, 12))) for _ in range(100)))
            rng.shuffle(terms)
            trie = CompressedTrie()
            for i, term in enumerate(terms):
                trie.insert(term, i)
            mapping = dict(zip(terms, range(len(terms))))
            seen = {}
            stack = [(trie.root, '')]
            while stack:
                node, prefix = stack.pop()
                if node.posting_index is not None:
                    seen[prefix] = node.posting_index
                if node is not trie.root and node.posting_index is None:
                    self.assertGreaterEqual(len(node.edges), 2)
                for first, (label, child) in node.edges.items():
                    self.assertTrue(label)
                    self.assertEqual(first, label[0])
                    stack.append((child, prefix + label))
            self.assertEqual(seen, mapping)
            for term, index in mapping.items():
                self.assertEqual(trie.lookup(term), index)

    def test_intersection_against_sets(self):
        rng = random.Random(17)
        for _ in range(500):
            a = sorted(rng.sample(range(100), rng.randrange(101)))
            b = sorted(rng.sample(range(100), rng.randrange(101)))
            self.assertEqual(intersect(a, b), sorted(set(a) & set(b)))

    def test_edge_cases_and_result_isolation(self):
        engine = SearchEngine(self.docs[:20])
        for query in ('', '  ', '!!!', 'AND', 'unicorn', 'graph AND unicorn', 'graph apple'):
            self.assertEqual(engine.and_ids(query), [])
        for query in ('graph graph', 'GRAPH, graph!', 'graph AND graph'):
            self.assertEqual(engine.and_ids(query), [2, 3, 5])
        self.assertEqual(engine.and_ids('data AND algorithm'), [1, 4, 6])
        self.assertEqual(engine.and_ids('graph AND search AND path'), [3, 5])
        self.assertEqual(engine.keyword_ids('Graph!'), [2, 3, 5])
        self.assertEqual(engine.keyword_ids('graph search'), [])
        engine.keyword_ids('graph').clear()
        engine.and_ids('graph').clear()
        self.assertEqual(engine.keyword_ids('graph'), [2, 3, 5])
        self.assertEqual(engine.matches([2]), [(2, 'Graph Data')])
        self.assertEqual(SearchEngine([]).and_ids('graph'), [])
        with self.assertRaises(ValueError):
            SearchEngine([self.docs[0], self.docs[0]])
        for cls in (StandardTrie, CompressedTrie):
            with self.assertRaises(ValueError):
                cls().insert('', 0)

    def test_interactive_repeated_words_and_operator(self):
        output = io.StringIO()
        with patch('builtins.input', side_effect=['graph graph', 'data AND algorithm', '!!!', '']), contextlib.redirect_stdout(output):
            main()
        lines = output.getvalue().splitlines()
        self.assertIn("(2, 'Graph Data')", lines[1])
        self.assertIn("(5, 'Graph Search')", lines[1])
        self.assertIn("(6, 'Data Algorithms')", lines[2])
        self.assertEqual(lines[3], 'No matches')

    def test_interactive_eof(self):
        with patch('builtins.input', side_effect=EOFError), contextlib.redirect_stdout(io.StringIO()):
            main()


if __name__ == '__main__':
    unittest.main(verbosity=2)
