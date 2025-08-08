import os, sys; sys.path.append(os.path.dirname(os.path.dirname(__file__)))
#!/usr/bin/env python3
import argparse, os, random, glob, json
from transformers import AutoTokenizer

def main():
    ap = argparse.ArgumentParser(description="Estimate tokens for a corpus using a model tokenizer")
    ap.add_argument("path", help="Directory to scan for text-like files")
    ap.add_argument("--glob", default="**/*.txt", help="Glob pattern (default: **/*.txt)")
    ap.add_argument("--sample", type=int, default=1000, help="Sample size (default: 1000 files)")
    ap.add_argument("--model", default="BAAI/bge-base-en-v1.5", help="HF tokenizer model name")
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model)
    files = glob.glob(os.path.join(args.path, args.glob), recursive=True)
    if not files:
        print("No files matched.")
        return
    random.shuffle(files)
    files = files[: args.sample]

    total_tokens = 0
    total_bytes = 0
    counted = 0
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            total_bytes += len(txt.encode("utf-8", "ignore"))
            total_tokens += len(tok.encode(txt, add_special_tokens=False))
            counted += 1
        except Exception:
            continue

    avg_tokens = total_tokens / max(1, counted)
    avg_bytes = total_bytes / max(1, counted)
    print(json.dumps({
        "files_counted": counted,
        "avg_tokens_per_file": avg_tokens,
        "avg_bytes_per_file": avg_bytes,
        "est_tokens_total_for_dir": avg_tokens * len(files),
    }, indent=2))

if __name__ == "__main__":
    main()
