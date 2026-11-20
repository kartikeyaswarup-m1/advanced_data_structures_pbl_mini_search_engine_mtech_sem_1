"""Mini search engine: inverted files, standard Trie, compressed radix Trie."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field


def tokenize(text: str) -> list[str]:
    """ASCII letters/digits, lowercase; punctuation separates tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def inverted_index(documents: list[dict]) -> tuple[list[str], list[list[int]]]:
    postings: dict[str, set[int]] = {}
    for document in documents:
        for term in set(tokenize(document["text"])):
            postings.setdefault(term, set()).add(document["id"])
    terms = sorted(postings)
    return terms, [sorted(postings[term]) for term in terms]


@dataclass
class StandardNode:
    children: dict[str, StandardNode] = field(default_factory=dict)
    posting_index: int | None = None


class StandardTrie:
    def __init__(self):
        self.root = StandardNode()

    def insert(self, term: str, posting_index: int) -> None:
        if not term:
            raise ValueError("empty index term")
        node = self.root
        for character in term:
            if character not in node.children:
                node.children[character] = StandardNode()
            node = node.children[character]
        node.posting_index = posting_index

    def lookup(self, term: str) -> int | None:
        if not term:
            return None
        node = self.root
        for character in term:
            node = node.children.get(character)
            if node is None:
                return None
        return node.posting_index


@dataclass
class RadixNode:
    # Each edge key is its first character; the edge value is (full label, child).
    edges: dict[str, tuple[str, RadixNode]] = field(default_factory=dict)
    posting_index: int | None = None



class CompressedTrie:
    def __init__(self):
        self.root = RadixNode()

    def insert(self, term: str, posting_index: int) -> None:
        if not term:
            raise ValueError("empty index term")
        node, offset = self.root, 0
        while offset < len(term):
            first = term[offset]
            edge = node.edges.get(first)
            if edge is None:
                node.edges[first] = (term[offset:], RadixNode(posting_index=posting_index))
                return
            label, child = edge
            shared = 0
            while (shared < len(label) and offset + shared < len(term)
                   and label[shared] == term[offset + shared]):
                shared += 1
            if shared == len(label):
                node, offset = child, offset + shared
                continue
            # Split once, preserving an existing term and its descendants.
            middle = RadixNode()
            node.edges[first] = (label[:shared], middle)
            old_suffix = label[shared:]
            middle.edges[old_suffix[0]] = (old_suffix, child)
            offset += shared
            if offset < len(term):
                suffix = term[offset:]
                middle.edges[suffix[0]] = (suffix, RadixNode(posting_index=posting_index))
            else:
                middle.posting_index = posting_index
            return
        node.posting_index = posting_index

    def lookup(self, term: str) -> int | None:
        if not term:
            return None
        node, offset = self.root, 0
        while offset < len(term):
            edge = node.edges.get(term[offset])
            if edge is None:
                return None
            label, child = edge
            if not term.startswith(label, offset):
                return None
            offset, node = offset + len(label), child
        return node.posting_index


def intersect(left: list[int], right: list[int]) -> list[int]:
    """Linear two-pointer intersection of sorted, unique posting lists."""
    result: list[int] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            result.append(left[i])
            i += 1
            j += 1
        elif left[i] < right[j]:
            i += 1
        else:
            j += 1
    return result


class SearchEngine:
    def __init__(self, documents: list[dict]):
        ids = [doc["id"] for doc in documents]
        if len(ids) != len(set(ids)):
            raise ValueError("document IDs must be unique")
        self.documents = {doc["id"]: doc for doc in documents}
        self.terms, self.postings = inverted_index(documents)
        self.standard = StandardTrie()
        self.compressed = CompressedTrie()
        for i, term in enumerate(self.terms):
            self.standard.insert(term, i)
            self.compressed.insert(term, i)

    def keyword_ids(self, query: str) -> list[int]:
        words = tokenize(query)
        if len(words) != 1:
            return []
        i = self.compressed.lookup(words[0])
        return self.postings[i].copy() if i is not None else []

    def and_ids(self, query: str) -> list[int]:
        # Repeated query terms have no effect on AND semantics.
        words = list(dict.fromkeys(
            word for word in tokenize(query) if word != "and"
        ))
        if not words:
            return []
        indexes = [self.compressed.lookup(word) for word in words]
        if any(i is None for i in indexes):
            return []
        lists = sorted((self.postings[i] for i in indexes), key=len)
        result = lists[0].copy()
        for posting in lists[1:]:
            result = intersect(result, posting)
            if not result:
                break
        return result

    def matches(self, ids: list[int]) -> list[tuple[int, str]]:
        return [(id_, self.documents[id_]["title"]) for id_ in ids]


def counts(root: StandardNode | RadixNode) -> tuple[int, int]:
    nodes, edges = 0, 0
    stack = [root]
    while stack:
        node = stack.pop()
        nodes += 1
        children = (child for _, child in node.edges.values()) if isinstance(node, RadixNode) else node.children.values()
        for child in children:
            edges += 1
            stack.append(child)
    return nodes, edges


def deep_size(obj: object) -> int:
    """Approximate reachable Python object size, counting shared objects once."""
    seen: set[int] = set()
    def size(value: object) -> int:
        if id(value) in seen:
            return 0
        seen.add(id(value))
        total = sys.getsizeof(value)
        if isinstance(value, dict):
            return total + sum(size(k) + size(v) for k, v in value.items())
        if isinstance(value, (tuple, list, set)):
            return total + sum(size(v) for v in value)
        if isinstance(value, (StandardNode, RadixNode)):
            return total + size(vars(value))
        return total
    return size(obj)
