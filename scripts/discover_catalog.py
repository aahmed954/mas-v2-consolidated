#!/usr/bin/env python3
import os, sys, json, time, subprocess, mimetypes, math, hashlib
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/starlord/mas-v2-crewai/cases_to_process")
OUT  = Path(sys.argv[2] if len(sys.argv) > 2 else "catalog-summary.json")

TEXT_EXT  = {".txt", ".md", ".log", ".csv", ".json", ".xml", ".html", ".htm", ".yml", ".yaml"}
PDF_EXT   = {".pdf"}
IMG_EXT   = {".png",".jpg",".jpeg",".tif",".tiff",".bmp",".gif",".webp"}
AUDIO_EXT = {".mp3",".wav",".m4a",".aac",".flac",".ogg",".opus"}
VIDEO_EXT = {".mp4",".mov",".mkv",".avi",".m4v",".webm"}

def ffprobe_duration(path: Path) -> float:
    try:
        p = subprocess.run(
            ["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30
        )
        return float(p.stdout.strip())
    except Exception:
        return 0.0

def pdf_page_count(path: Path) -> int:
    # Use 'pdfinfo' if available for speed; fallback rough guess
    try:
        p = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=20)
        for line in p.stdout.splitlines():
            if line.lower().startswith("pages:"):
                return int(line.split(":")[1].strip())
    except Exception:
        pass
    return 0

def approx_tokens_from_bytes(nbytes: int) -> int:
    # Very rough: 1 token ~ 4 chars; assume UTF-8 1 byte/char avg for plain text
    return max(1, nbytes // 4)

def main():
    t0 = time.time()
    if not ROOT.exists():
        print(f"Directory not found: {ROOT}", file=sys.stderr)
        sys.exit(2)

    totals = dict(files=0, bytes=0, tokens_est=0, pdf_pages=0, audio_sec=0.0, video_sec=0.0, images=0)
    by_type = Counter()
    by_ext  = Counter()
    largest = []

    for dirpath, _, files in os.walk(ROOT):
        for name in files:
            p = Path(dirpath) / name
            try:
                st = p.stat()
            except Exception:
                continue
            ext = p.suffix.lower()
            size = st.st_size
            totals["files"] += 1
            totals["bytes"] += size
            by_ext[ext] += 1

            if ext in TEXT_EXT:
                by_type["text"] += 1
                totals["tokens_est"] += approx_tokens_from_bytes(size)

            elif ext in PDF_EXT:
                by_type["pdf"] += 1
                pages = pdf_page_count(p)
                totals["pdf_pages"] += pages
                # token estimate ~ 600 tokens per PDF page (typical OCR/page)
                totals["tokens_est"] += pages * 600

            elif ext in IMG_EXT:
                by_type["image"] += 1
                totals["images"] += 1
                # token estimate for OCR ~ 150 words ~ 200 tokens/image (very rough)
                totals["tokens_est"] += 200

            elif ext in AUDIO_EXT:
                by_type["audio"] += 1
                dur = ffprobe_duration(p)
                totals["audio_sec"] += dur
                # transcription tokens ~ 3.2 tokens/sec average English speech
                totals["tokens_est"] += int(dur * 3.2)

            elif ext in VIDEO_EXT:
                by_type["video"] += 1
                dur = ffprobe_duration(p)
                totals["video_sec"] += dur
                totals["tokens_est"] += int(dur * 3.2)

            else:
                by_type["other"] += 1
                # conservative minimal bump
                totals["tokens_est"] += approx_tokens_from_bytes(min(size, 5_000))

            largest.append((size, str(p)))
            if len(largest) > 50:
                largest = sorted(largest, reverse=True)[:50]

    # cost estimate with our model price (BAAI/bge-base-en-v1.5-vllm @ $0.008/M)
    price_per_million = 0.008
    tokens = totals["tokens_est"]
    cost = (tokens/1_000_000.0)*price_per_million

    summary = {
        "root": str(ROOT),
        "totals": totals,
        "by_type": dict(by_type),
        "by_ext": dict(by_ext.most_common(50)),
        "largest_files": [{"bytes":b,"path":p} for b,p in sorted(largest, reverse=True)],
        "pricing": {"model":"BAAI/bge-base-en-v1.5-vllm","price_per_million_tokens":price_per_million,"est_cost_usd": round(cost,6)},
        "elapsed_sec": round(time.time()-t0,2),
        "notes": [
            "Token estimates are rough; actual bill is Together input tokens only.",
            "Video/audio token estimate uses ~3.2 tokens/sec speech rate.",
            "PDF page tokens ~600/page; images ~200 tokens/image if OCR text.",
        ],
    }
    with open(OUT, "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()