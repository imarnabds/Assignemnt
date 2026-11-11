#!/usr/bin/env python3
"""Small standard-library concurrent HTTP load generator for the HPA exercise."""
import argparse
import concurrent.futures
import json
import time
import urllib.error
import urllib.request

def hit(url, index):
    payload = json.dumps({"loadTest": True, "request": index}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/data",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
            return response.status
    except (urllib.error.URLError, TimeoutError) as exc:
        return f"ERROR: {exc}"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=50)
    args = parser.parse_args()
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda i: hit(args.url, i), range(args.requests)))
    elapsed = time.time() - start
    successes = sum(result == 201 for result in results)
    failures = len(results) - successes
    print(json.dumps({
        "url": args.url,
        "requests": args.requests,
        "workers": args.workers,
        "successes_http_201": successes,
        "failures": failures,
        "elapsed_seconds": round(elapsed, 2),
        "requests_per_second": round(len(results) / elapsed, 2) if elapsed else None,
        "status_counts": {str(s): results.count(s) for s in set(results)},
    }, indent=2))

if __name__ == "__main__":
    main()
