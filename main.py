"""Interactive search demo. Run: python3 main.py"""
from corpus import load_documents

from search_engine import SearchEngine


def main():
    docs = load_documents()
    engine = SearchEngine(docs)
    print(f"Mini Search Engine: {len(docs)} documents. Enter words separated by spaces or AND; blank line exits.")
    while True:
        try:
            query = input("search> ")
        except EOFError:
            break
        if not query.strip():
            break
        ids = engine.and_ids(query)
        print(engine.matches(ids) if ids else "No matches")


if __name__ == "__main__":
    main()
