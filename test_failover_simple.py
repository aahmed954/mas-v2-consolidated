#!/usr/bin/env python3
"""Simple test for embedding failover."""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

# First test with good API key
print("1. Testing with valid API key (should use Together):")
os.environ["TOGETHER_API_KEY"] = "tgp_v1_peF7JytuY7bC2uMRmsZxglftyn4t2Py4YYXYqDwZzMk"
from src.embeddings.providers import FallbackEmbeddingClient
client = FallbackEmbeddingClient()
result = client.embed(["Hello world"])
print(f"   Provider: {result['provider']}")

# Test with bad API key (should failover to local)
print("\n2. Testing with bad API key (should failover to local):")
os.environ["TOGETHER_API_KEY"] = "bad_key"
client2 = FallbackEmbeddingClient()
result2 = client2.embed(["Failover test"])
print(f"   Provider: {result2['provider']}")

# Test local endpoint directly
print("\n3. Testing local endpoint directly:")
import requests
r = requests.post("http://localhost:8085/embeddings", 
                  json={"input": ["Local test"]})
print(f"   Status: {r.status_code}")
print(f"   Response keys: {list(r.json().keys())}")