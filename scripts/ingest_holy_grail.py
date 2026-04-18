#!/usr/bin/env python
# scripts/ingest_holy_grail.py
"""Ingest the Bucket Holy Grail documents into the persistent ChromaDB index."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from autoso.pipeline.holy_grail import ingest_holy_grail

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/ingest_holy_grail.py <file_or_directory>")
        sys.exit(1)

    path = sys.argv[1]
    if not Path(path).exists():
        print(f"Path not found: {path}")
        sys.exit(1)

    print(f"Ingesting {path}...")
    ingest_holy_grail(path)
    print("Done. Holy Grail index is ready.")
