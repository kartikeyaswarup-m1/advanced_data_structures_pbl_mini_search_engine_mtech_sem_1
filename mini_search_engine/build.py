"""Generate the dataset, evidence, visualizations, and repeatable measurements."""
import csv
import json
import platform
import sys
import unittest
from html import escape
import statistics
import subprocess
import time
from pathlib import Path

from search_engine import (CompressedTrie, SearchEngine, StandardTrie, counts,
                           deep_size, intersect, inverted_index, tokenize)

HERE = Path(__file__).resolve().parent
OUT = HERE / "evidence"
from corpus import benchmark_documents as documents


def verify(engine: SearchEngine) -> list[tuple[str, str, list[int]]]:
    checks = [
        ("known", "graph", [2, 3, 5]),
        ("unknown", "unicorn", []),
        ("prefix exact", "app", [7, 8]),
        ("prefix longer", "apple", [7]),
        ("prefix absent", "appl", []),
        ("AND matches", "data algorithm", [1, 4, 6]),
        ("AND no matches", "graph apple", []),
        ("AND 3 terms", "graph search path", [3, 5]),
        ("repeated keyword", "graph graph search", [3, 5]),
        ("only repeated keyword", "graph graph", [2, 3, 5]),
        ("explicit AND", "data AND algorithm", [1, 4, 6]),
        ("case and punctuation", "GRAPH, search!", [3, 5]),
        ("punctuation only", "!!!", []),
        ("empty input", "  ", []),
        ("missing AND term", "graph unicorn", []),
    ]
    for name, query, expected in checks:
        actual = (engine.keyword_ids(query) if name in
                  ("known", "unknown", "prefix exact", "prefix longer", "prefix absent")
                  else engine.and_ids(query))
        assert actual == expected, (name, actual, expected)
    for i, term in enumerate(engine.terms):
        assert engine.standard.lookup(term) == i
        assert engine.compressed.lookup(term) == i
        expected = [id_ for id_, doc in engine.documents.items() if term in set(tokenize(doc["text"]))]
        assert engine.postings[i] == sorted(expected)
    for absent in ("", "appl", "tr", "zzzz", "graphical"):
        assert engine.standard.lookup(absent) is None
        assert engine.compressed.lookup(absent) is None
    assert intersect([1, 3, 4, 6], [1, 2, 4, 6]) == [1, 4, 6]
    assert all(v == sorted(set(v)) for v in engine.postings)
    return checks


def tree_records(root, compressed: bool):
    """Full tree in preorder, with stable IDs and reconstructed term prefixes."""
    records = []
    def visit(node, parent, label, prefix, depth):
        index = len(records)
        records.append((node, parent, label, prefix, depth))
        children = (node.edges.values() if compressed else node.children.items())
        for edge, child in sorted(children, key=lambda item: item[0]):
            visit(child, index, edge, prefix + edge, depth + 1)
    visit(root, None, "", "", 0)
    return records


def write_dot(root, compressed: bool, path: Path) -> None:
    records = tree_records(root, compressed)
    lines = ['digraph Trie {', 'rankdir=LR; node [shape=box, fontsize=10];']
    for i, (node, parent, label, prefix, depth) in enumerate(records):
        name = f"{prefix or 'root'}" + (f" / list[{node.posting_index}]" if node.posting_index is not None else "")
        color = '#dcfce7' if node.posting_index is not None else '#f1f5f9'
        lines.append(f'n{i} [label={json.dumps(name)}, style=filled, fillcolor="{color}"];')
        if parent is not None:
            lines.append(f'n{parent} -> n{i} [label={json.dumps(label)}];')
    lines.append('}')
    path.write_text("\n".join(lines) + "\n")


def render_tree_svg(root, compressed: bool, path: Path) -> None:
    """Complete dependency-free tree; subtree layout keeps branches separate."""
    records = tree_records(root, compressed)
    children = {i: [] for i in range(len(records))}
    for i, (_, parent, _, _, _) in enumerate(records):
        if parent is not None:
            children[parent].append(i)
    positions = {}
    next_leaf = 0
    def place(i):
        nonlocal next_leaf
        ys = [place(child) for child in children[i]]
        if ys:
            y = (ys[0] + ys[-1]) / 2
        else:
            y = 95 + next_leaf * 74
            next_leaf += 1
        positions[i] = (35 + records[i][4] * 235, y)
        return y
    place(0)
    width = 230 + max(r[4] for r in records) * 235
    height = 125 + max(1, next_leaf) * 74
    title = 'Compressed Trie' if compressed else 'Standard Trie'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<style>text{font:12px sans-serif;fill:#172554} path{fill:none;stroke:#94a3b8}</style>',
             f'<text x="25" y="25" font-size="18">{title}: complete initial 20-document vocabulary</text>',
             '<text x="25" y="48">Green nodes store posting-array indices; edge labels are indexed characters. Zoom to inspect.</text>']
    for i, (node, parent, label, prefix, depth) in enumerate(records):
        x, y = positions[i]
        if parent is not None:
            px, py = positions[parent]
            parts.append(f'<path d="M {px+100} {py} H {x-110} V {y} H {x}"/>')
            parts.append(f'<text x="{x-8}" y="{y-8}" text-anchor="end">{escape(label)}</text>')
        fill = '#dcfce7' if node.posting_index is not None else '#f1f5f9'
        parts.append(f'<g><title>{escape(prefix or "root")}</title><rect x="{x}" y="{y-17}" width="100" height="34" rx="5" fill="{fill}" stroke="#334155"/>')
        name = f'list[{node.posting_index}]' if node.posting_index is not None else f'node {i}'
        parts.append(f'<text x="{x+50}" y="{y+4}" text-anchor="middle">{name}</text></g>')
    parts.append('</svg>')
    path.write_text("\n".join(parts))


def median_us(fn, repetitions: int, rounds: int = 7) -> float:
    # ns precision; repeated batch amortizes timer and call overhead.
    times = []
    for _ in range(rounds):
        start = time.perf_counter_ns()
        for _ in range(repetitions):
            fn()
        times.append((time.perf_counter_ns() - start) / repetitions / 1000)
    return statistics.median(times)


def benchmark() -> list[dict]:
    rows = []
    for n in (10, 25, 50, 100):
        docs = documents(n)
        terms, postings = inverted_index(docs)
        engine = SearchEngine(docs)
        for i, term in enumerate(terms):
            assert engine.standard.lookup(term) == engine.compressed.lookup(term) == i
        assert engine.standard.lookup("neverindexed") is None
        assert engine.compressed.lookup("neverindexed") is None
        std_nodes, std_edges = counts(engine.standard.root)
        cmp_nodes, cmp_edges = counts(engine.compressed.root)
        row = {"documents": n, "terms": len(terms), "posting_entries": sum(map(len, postings)),
               "standard_nodes": std_nodes, "standard_edges": std_edges,
               "compressed_nodes": cmp_nodes, "compressed_edges": cmp_edges,
               "standard_trie_bytes": deep_size(engine.standard.root),
               "compressed_trie_bytes": deep_size(engine.compressed.root),
               "posting_array_bytes": deep_size(engine.postings),
               "index_build_us": median_us(lambda: inverted_index(docs), 200),
               "standard_build_us": median_us(lambda: build_trie(StandardTrie, terms), 200),
               "compressed_build_us": median_us(lambda: build_trie(CompressedTrie, terms), 200),
               "standard_lookup_us": median_us(lambda: engine.standard.lookup("search"), 20000),
               "compressed_lookup_us": median_us(lambda: engine.compressed.lookup("search"), 20000),
               "single_search_us": median_us(lambda: engine.keyword_ids("search"), 10000),
               "and_search_us": median_us(lambda: engine.and_ids("data search"), 10000)}
        rows.append(row)
    return rows


def build_trie(cls, terms):
    trie = cls()
    for i, term in enumerate(terms):
        trie.insert(term, i)
    return trie


def chart(rows: list[dict], field: str, name: str, unit: str) -> None:
    width, height = 740, 410
    maximum = max(r[field] for r in rows) * 1.18
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<style>text{font:14px sans-serif;fill:#172554}</style>',
             f'<text x="30" y="28" font-size="18">{name} ({unit})</text>',
             '<line x1="65" y1="345" x2="700" y2="345" stroke="#334155"/>',
             '<line x1="65" y1="55" x2="65" y2="345" stroke="#334155"/>']
    for j, row in enumerate(rows):
        x = 120 + j * 145
        h = 280 * row[field] / maximum
        parts.extend([f'<rect x="{x}" y="{345-h:.1f}" width="70" height="{h:.1f}" fill="#2563eb"/>',
                      f'<text x="{x+35}" y="{335-h:.1f}" text-anchor="middle">{row[field]:.2f}</text>',
                      f'<text x="{x+35}" y="370" text-anchor="middle">{row["documents"]} docs</text>'])
    parts.append('</svg>')
    (OUT / (name.lower().replace(" ", "_") + ".svg")).write_text("\n".join(parts))


def main():
    OUT.mkdir(exist_ok=True)
    # Run regression tests before overwriting generated evidence.
    suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py")
    with (OUT / "test_results.txt").open("w") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit("Regression tests failed; see evidence/test_results.txt")
    docs = documents(20)
    (HERE / "dataset_100.json").write_text(json.dumps(documents(100), indent=2) + "\n")
    engine = SearchEngine(docs)
    checks = verify(engine)
    (OUT / "posting_array.json").write_text(json.dumps(engine.postings, indent=2) + "\n")
    lines = ["# Inverted index (initial 20 documents)", "", "Term | Posting array index | Sorted document IDs", "--- | ---: | ---"]
    lines += [f"{term} | {i} | {engine.postings[i]}" for i, term in enumerate(engine.terms)]
    (OUT / "inverted_index.md").write_text("\n".join(lines) + "\n")
    (OUT / "checks.json").write_text(json.dumps([{"check": name, "query": query, "expected": result, "actual": (engine.keyword_ids(query) if name in ("known", "unknown", "prefix exact", "prefix longer", "prefix absent") else engine.and_ids(query)), "passed": True}
                                                  for name, query, result in checks], indent=2) + "\n")
    demo = []
    for query, method in (("graph", engine.keyword_ids), ("app", engine.keyword_ids),
                          ("data algorithm", engine.and_ids), ("graph apple", engine.and_ids),
                          ("graph graph search", engine.and_ids),
                          ("graph graph", engine.and_ids),
                          ("data AND algorithm", engine.and_ids),
                          ("graph search path", engine.and_ids),
                          ("unicorn", engine.keyword_ids),
                          ("", engine.and_ids)):
        demo.append(f"{query!r} -> {engine.matches(method(query))}")
    (OUT / "demo.txt").write_text("\n".join(demo) + "\n")
    queries = ["graph", "graph graph", "data AND algorithm", "graph search path",
               "graph apple", "unicorn", "!!!", ""]
    run = subprocess.run([sys.executable, "-B", str(HERE / "main.py")],
                         input="\n".join(queries) + "\n", text=True,
                         capture_output=True, check=True)
    (OUT / "interactive_demo.txt").write_text(
        "Inputs, in order: " + json.dumps(queries) + "\n\n" + run.stdout)
    for trie, compressed, name in ((engine.standard.root, False, "standard_trie"),
                                    (engine.compressed.root, True, "compressed_trie")):
        write_dot(trie, compressed, OUT / f"{name}.dot")
        render_tree_svg(trie, compressed, OUT / f"{name}.svg")
    rows = benchmark()
    metadata = {
        "python": sys.version, "platform": platform.platform(),
        "timer": "perf_counter_ns", "rounds": 7, "aggregation": "median microseconds per call",
        "build_batch": 200, "lookup_batch": 20000, "search_batch": 10000,
        "lookup_term": "search", "and_query": "data search",
        "corpus_sizes": [10, 25, 50, 100],
        "memory": "reachable sys.getsizeof objects counted once per root; excludes process RSS and documents",
        "regression_tests": result.testsRun,
        "corpus_source": "documents/*.txt (UTF-8 bodies; ID and title headers excluded)",
        "expansion": "20 initial files; repeated paragraph topics for IDs above the initial corpus",
    }
    (OUT / "benchmark_environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    fields = list(rows[0])
    (OUT / "comparison_table.txt").write_text(
        " | ".join(fields) + "\n" + "\n".join(
            " | ".join(f"{row[f]:.4f}" if isinstance(row[f], float) else str(row[f]) for f in fields)
            for row in rows) + "\n")
    with (OUT / "measurements.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    for field, title, unit in (("index_build_us", "Index construction", "microseconds"),
                                ("compressed_build_us", "Compressed Trie construction", "microseconds"),
                                ("single_search_us", "Single keyword search", "microseconds"),
                                ("and_search_us", "AND search", "microseconds"),
                                ("compressed_nodes", "Compressed Trie nodes", "count"),
                                ("standard_nodes", "Standard Trie nodes", "count"),
                                ("standard_build_us", "Standard Trie construction", "microseconds"),
                                ("standard_lookup_us", "Standard Trie lookup", "microseconds"),
                                ("compressed_lookup_us", "Compressed Trie lookup", "microseconds")):
        chart(rows, field, title, unit)
    print(f"PASS: {len(checks)} named checks, all {len(engine.terms)} term lookups and posting lists")
    print(f"Generated {len(rows)} benchmark rows in {OUT}")


if __name__ == "__main__":
    main()
