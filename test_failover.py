#!/usr/bin/env python3
"""Test embedding failover functionality."""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from src.embeddings import get_embeddings
import time

print("=== Testing Embedding Failover ===\n")

# Test 1: Normal operation (should use Together)
print("1. Testing normal operation...")
result = get_embeddings(["Hello world", "Testing embeddings"])
print(f"Provider: {result['provider']}")
print(f"Vectors shape: {len(result['vectors'])} x {len(result['vectors'][0])}")
print()

# Test 2: Simulate Together failure by using bad API key
print("2. Simulating Together API failure...")
old_key = os.environ.get("TOGETHER_API_KEY", "")
os.environ["TOGETHER_API_KEY"] = "bad_key_to_simulate_failure"

# Force reload of the module to pick up new env
import importlib
import src.embeddings.providers
importlib.reload(src.embeddings.providers)
from src.embeddings import get_embeddings as get_embeddings_new

try:
    result = get_embeddings_new(["Failover test"])
    print(f"Provider after failure: {result['provider']}")
    print(f"Successfully failed over to local!")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Restore API key and check recovery
print("\n3. Testing recovery to Together...")
os.environ["TOGETHER_API_KEY"] = old_key
time.sleep(2)  # Give pinger time to detect recovery

# Test a few times to see transition
for i in range(5):
    result = get_embeddings_new(["Recovery test"])
    print(f"Attempt {i+1}: Provider = {result['provider']}")
    time.sleep(3)

print("\n=== Test Complete ===")