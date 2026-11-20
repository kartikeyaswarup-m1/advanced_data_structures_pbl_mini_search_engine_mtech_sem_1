# Evaluation and explanation

## Index and correctness

The initial collection contains 20 documents and 38 distinct terms. `dataset_100.json` contains all 100 documents, ordered by ID; the first 10, 25, 50, or 100 form the four collections. The term-to-array-position mapping and each sorted posting list appear in `evidence/inverted_index.md` and `evidence/posting_array.json`.

The program checks 11 named cases: known term, unknown term, three prefix cases, AND with matches, AND without matches, three-term AND, repeated query term, empty input, and a missing AND term. It checks both Trie lookups against every term's array position and independently computes each expected posting list by scanning the initial documents. For each benchmark corpus it also verifies every term in both Tries and a missing term. `evidence/checks.json` records the named checks.

Examples from the 20-document collection:

| Query | IDs | Interpretation |
| --- | --- | --- |
| `graph` | [2, 3, 5] | Single word |
| `app` | [7, 8] | Exact prefix word |
| `apple` | [7] | Longer word sharing a prefix |
| `data algorithm` | [1, 4, 6] | Two-list intersection |
| `graph apple` | [] | No shared documents |
| `graph graph search` | [3, 5] | Repeated word ignored |

## Measurement method

`build.py` uses `time.perf_counter_ns()`. It runs each operation in a batch, repeats the batch seven times, divides elapsed time by the batch size, and records the median in microseconds. Index and Trie builds use 200 calls per batch; lookup uses 20,000; complete single and AND searches use 10,000. Each timed index build starts with the same existing document objects and creates fresh posting lists. Each timed Trie build creates a new Trie from the same already extracted terms. Search measurements reuse the constructed engine. Construction timings do not include document generation, JSON I/O or graph rendering. The fixed lookup term is `search`; the AND query is `data search`.

Node and edge counts include the root. `deep_size` recursively sums `sys.getsizeof` of reachable Python objects, including dictionaries, edge-label strings and list objects, counting each object once. It reports the two Trie roots and the posting-list array separately. This is an **estimate for this Python interpreter**, not actual process RSS or a portable byte count. Python allocator overhead and external interpreter state are outside this estimate; title/document objects are excluded from these three columns.

## Counts and memory (sample run)

| Documents | Terms | Posting entries | Standard nodes / edges | Compressed nodes / edges | Standard Trie bytes | Compressed Trie bytes | Posting array bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 20 | 40 | 106 / 105 | 27 / 26 | 33,439 | 10,237 | 2,608 |
| 25 | 41 | 120 | 223 / 222 | 63 / 62 | 69,193 | 23,218 | 5,676 |
| 50 | 41 | 320 | 223 / 222 | 63 / 62 | 69,193 | 23,218 | 7,656 |
| 100 | 41 | 720 | 223 / 222 | 63 / 62 | 69,193 | 23,218 | 12,000 |

These memory values reflect the sample run; rerunning on another Python version can change them. The vocabulary stops growing after 25 documents, so Trie sizes stay constant while posting lists grow. On the 100-document corpus, path compression reduces nodes from 223 to 63. A node holding a word may also have descendants; the green nodes in the preview diagrams indicate such stored words.

## Times (sample run, microseconds per operation)

| Documents | Index build | Standard Trie build | Compressed Trie build | Standard lookup | Compressed lookup | Single search | AND search |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 13.66 | 23.49 | 12.71 | 0.256 | 0.275 | 0.662 | 2.566 |
| 25 | 38.40 | 52.59 | 31.20 | 0.256 | 0.370 | 0.768 | 3.475 |
| 50 | 89.76 | 52.60 | 31.12 | 0.262 | 0.374 | 0.809 | 4.860 |
| 100 | 189.96 | 52.68 | 31.09 | 0.256 | 0.372 | 0.800 | 7.152 |

The CSV is the full precision record. Timing bars are in SVG files. Small lookup times fluctuate with cache effects, system scheduling, and measurement overhead; these figures do not prove a consistent lookup speed advantage. Also, `single_search_us` includes copying the result list, while `*_lookup_us` measures only the Trie lookup. Trie construction time stays roughly stable from 25 to 100 because the vocabulary is fixed. Index construction grows with the number of tokens and posting entries.

## Complexity

Let **T** be total input tokens, **V** distinct terms, **L** total characters across distinct terms, **p** and **q** two posting-list lengths, and **k** the number of query terms. Hash-based term aggregation is expected O(T); sorting terms and posting lists adds O(V log V + sum of m_t log m_t), where m_t is a term's posting count. Both Trie builds take O(L) character work under expected constant-time dictionary access. Exact lookup scans the query characters in O(length of word), including comparison of compressed edge labels. A two-pointer intersection takes O(p + q) time and at most O(min(p, q)) output space. For k lists, ordering by length adds O(k log k), and repeated intersections take at most O(sum of examined list lengths plus intermediate scans); with a growing intersection, a safe bound is O(k × total posting entries read). More shared prefixes generally produce a larger reduction in compressed Trie nodes. Stored edge labels still take space, so node reduction does not imply the same percentage of memory reduction.

## Visualization scope

`standard_trie.svg` and `compressed_trie.svg` display the first two levels for legibility. Blue nodes have additional descendants. Their DOT files provide corresponding editable graph definitions. Full counts and exact lookup verification cover every node and term, not just the previewed levels. Search evidence is in `demo.txt`.
