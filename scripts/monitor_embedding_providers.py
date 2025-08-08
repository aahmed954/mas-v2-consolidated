#!/usr/bin/env python3
"""Monitor which embedding provider is being used."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from qdrant_client import QdrantClient
from collections import Counter
import argparse

def main():
    parser = argparse.ArgumentParser(description="Monitor embedding provider usage in Qdrant")
    parser.add_argument("--collection", default="mas_embeddings", help="Collection name")
    parser.add_argument("--host", default="localhost", help="Qdrant host")
    parser.add_argument("--port", type=int, default=6333, help="Qdrant port")
    args = parser.parse_args()
    
    client = QdrantClient(host=args.host, port=args.port)
    
    # Get collection info
    try:
        info = client.get_collection(args.collection)
        print(f"Collection: {args.collection}")
        print(f"Points count: {info.points_count}")
        print()
    except Exception as e:
        print(f"Error accessing collection: {e}")
        return
    
    # Sample some points to check providers
    offset = None
    providers = Counter()
    sample_size = min(1000, info.points_count)
    
    while len(providers) < sample_size:
        result = client.scroll(
            collection_name=args.collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )
        
        points, offset = result
        if not points:
            break
            
        for point in points:
            provider = point.payload.get("embedding_provider", "unknown")
            providers[provider] += 1
            
        if offset is None:
            break
    
    # Display results
    print("Embedding Provider Distribution:")
    print("-" * 40)
    total = sum(providers.values())
    for provider, count in providers.most_common():
        percentage = (count / total) * 100 if total > 0 else 0
        print(f"{provider:15} {count:6} ({percentage:5.1f}%)")
    
    print("-" * 40)
    print(f"Total sampled:  {total:6}")

if __name__ == "__main__":
    main()