# Mini Search Engine

Python 3.10+; standard library only. Run from this folder:

```bash
python3 build.py
python3 main.py
```

The first command reads the text files, exports the expanded benchmark dataset, recreates evidence, checks correctness, and measures performance. It does not overwrite your text documents. The second starts a 20-document interactive demo. Enter a single word or several words separated by spaces or the explicit `AND` operator. A blank line quits. For example, `graph`, `data algorithm`, or `graph graph search`, or `data AND algorithm`.

## Files

- `search_engine.py`: tokenization, inverted index, both Tries, two-pointer intersection, queries, counts, memory estimate.
- `build.py`: correctness checks, repeatable measurements, dataset export, DOT/SVG diagrams, charts and tables.
- `main.py`: interactive demonstration with document IDs and titles.
- `documents/`: the 20 initial UTF-8 `.txt` documents, each with a unique ID, title, and short paragraph. These are the source used by the search engine.
- `corpus.py`: text-file loading, metadata validation, and deterministic expansion for benchmarks.
- `dataset_100.json`: generated export of the 100-document benchmark collection. The interactive engine does not read this file.
- `evidence/inverted_index.md`: all 339 terms in the initial 20-document corpus and their posting-array references.
- `evidence/posting_array.json`: the corresponding array of sorted, unique posting lists. Array offsets start at zero.
- `evidence/checks.json`, `evidence/demo.txt`: correctness results and sample searches.
- `evidence/measurements.csv`: seven-round median timing and counts at four corpus sizes.
- `evidence/*.svg`: complete Trie diagrams and timing charts; `*.dot`: editable Trie graph sources.
- `test_search_engine.py`: independent document-scan comparisons, insertion-order and randomized Trie checks, intersection checks, and interactive regressions.
- `evidence/test_results.txt`: reproducible regression test output.
- `evidence/interactive_demo.txt`: transcript captured from the real CLI.
- `evidence/benchmark_environment.json`: interpreter/platform and benchmark configuration.
- `evidence/comparison_table.txt`: regenerated comparison table matching the CSV.
- `RESULTS.md`: original sample write-up; its tables and two-level-diagram description predate the current build. Current measurements are in `evidence/measurements.csv`; implementation bounds are below.

## Editing the documents

Open `documents/01_algorithm_fundamentals.txt` (or any of the other 19 files). Each file has this format:

```text
ID: 1
Title: Algorithm Fundamentals

An algorithm gives precise steps for solving a problem. Students organize data before a search, then use complexity analysis to estimate how much work the procedure requires as the collection grows.
```

The first line is a positive integer ID, the second is a nonempty title, and a blank line separates metadata from the body. Bodies can span multiple lines. Only body text is indexed. Filenames are descriptive; IDs come from the headers. Duplicate IDs, empty titles, missing bodies, or malformed headers produce an error.

After editing a body, restart `python3 main.py` to search the updated content. Run `python3 build.py` to refresh the export, inverted-index table, posting-array references, diagrams, and benchmarks. Keep exactly 20 source files for the prescribed benchmark setup. The hand-calculated sample checks assume the supplied corpus; intentional changes to its example keywords require updating those expected results.

## Design

Only document `text` is indexed; document titles are displayed in results. The tokenizer lowercases and extracts ASCII letter/digit runs (`[a-z0-9]+`); punctuation splits words. Each document ID is inserted once per distinct term; terms are sorted alphabetically and assigned positions in a separate posting-list array. A Trie node stores an integer array offset, never the posting list itself. A term that is also the prefix of another term has a posting index on a node with children, as in `app` and `apple`.

In the compressed Trie, an edge contains a whole substring. Insertion splits an existing edge when a new term diverges or ends inside it. Lookup requires full edge-label matches, so `appl` cannot accidentally match `apple`. AND search deduplicates query words and intersects sorted lists using two moving pointers; for more than two lists it intersects shortest first. Empty input returns no results in the engine; a blank line exits the CLI. In AND queries, the standalone token `and` is reserved as a separator (case insensitive); other tokens such as `android` are unchanged. `keyword_ids` remains a strict one-token API. Both `graph graph` and `graph AND graph` return the same matches as `graph`.

The complete SVG and DOT diagrams include every node of the initial 20-document index. Green nodes store `list[index]`, including words that are prefixes of other words; SVG hover titles show reconstructed terms. Open the SVG in a browser and zoom or scroll to inspect branches.

## Reproduce the checks

```bash
python3 -m unittest discover -v
python3 build.py
cat evidence/checks.json
cat evidence/demo.txt
cat evidence/measurements.csv
```

The corpus is synthetic. The initial 20 text files contain meaningful paragraphs. For benchmarks, the next 80 documents repeat those paragraph topics with an additional sentence and unique IDs/titles. Expanded documents are generated in memory and exported to JSON; they do not replace the 20 source files. Timing depends on the Python build, operating system and machine. Run `build.py` on the machine used for the presentation to refresh the CSV and charts. No search or Trie package is used.


## Implementation complexity

Let C be the number of input characters, T the number of tokens, V the vocabulary size, L the total characters in distinct index terms, P the total posting entries, and m_t the posting count for term t. Tokenization and expected hash aggregation cost O(C + T); sorting adds O(V log V) string comparisons and O(sum(m_t log m_t)) integer comparisons. String comparison costs depend on common-prefix lengths.

The standard Trie builds in O(L) expected time. Compressed insertion scans a word by offset, copying substrings only when creating or splitting an edge. One insertion takes O(m + e), where m is the new word length and e is the existing edge-label length if a split occurs; Python must copy that old label. Across a build a conservative bound is O(L + S), with S the total old-label characters copied during splits. Both exact lookups take O(m) expected time; compressed lookup uses `startswith(label, offset)` without making suffix copies.

For one keyword, retrieving IDs costs O(m + p), including copying its p results; displaying titles adds O(p). Two sorted lists intersect in O(p + q) time and O(min(p, q)) output space. For k distinct AND terms, let Q be total query characters and R the sum of the selected posting lengths. Normalization/lookup, length sorting, and sequential intersections take O(Q + k log k + R) expected time. Every intermediate intersection can only shrink; starting with the shortest list bounds intermediate scans by R. Peak intersection workspace is O(s), where s is the shortest posting length, plus O(Q + k) query storage.

The standard Trie has O(L) nodes and edges. The compressed Trie has O(V) structural nodes and edges, with O(L) stored edge-label characters and O(V) terminal references. The separate posting array takes O(V + P) storage. Memory columns estimate reachable Python objects independently for each root, so shared objects can appear in more than one column; do not treat their sum as an exact process-memory measurement.

The synthetic vocabulary is fixed after 25 documents, so larger collections test posting-list growth rather than continuing vocabulary growth. Fixed-query timings describe the documented workload and are not a general speed ranking.
