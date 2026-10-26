import json
import os
import random
import time
import urllib.error
import urllib.request

URLS = [
    url.strip()
    for url in os.environ.get("APP_URLS", "http://app-a:8000,http://app-b:8000").split(",")
    if url.strip()
]
ids = {url: [] for url in URLS}

# seconds, total RPS, share of failing requests
RAMP = [(60, 5, 0.01)]
LOOP = [(60, 15, 0.01), (60, 45, 0.05)]


def phases():
    yield from RAMP
    while True:
        yield from LOOP


def call(method, url, body=None, force_status=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if force_status:
        request.add_header("X-Force-Status", force_status)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def one_request(error_rate):
    base = random.choice(URLS)
    roll = random.random()
    if roll < error_rate:
        status_code = "404" if roll < error_rate / 2 else "500"
        method = random.choice(["POST", "GET", "PUT"])
        if method == "POST":
            call("POST", f"{base}/items", {"name": "boom"}, status_code)
        else:
            body = {"name": "missing"} if method == "PUT" else None
            call(method, f"{base}/items/missing-{random.randrange(1_000_000)}", body, status_code)
        return
    kind = random.choice(["post", "get", "put", "delete"])
    known = ids[base]
    if kind == "post" or not known:
        status, raw = call("POST", f"{base}/items", {"name": "load"})
        if status in (200, 201):
            ids[base].append(json.loads(raw)["id"])
        return
    item_id = random.choice(known)
    if kind == "get":
        call("GET", f"{base}/items/{item_id}")
    elif kind == "put":
        call("PUT", f"{base}/items/{item_id}", {"name": "updated"})
    else:
        status, _ = call("DELETE", f"{base}/items/{item_id}")
        if status == 200:
            known.remove(item_id)


def run(seconds, rps, error_rate):
    print(f"phase {seconds}s rps={rps} errors={error_rate}", flush=True)
    deadline = time.monotonic() + seconds
    next_at = time.monotonic()
    interval = 1 / rps
    while time.monotonic() < deadline:
        one_request(error_rate)
        next_at += interval
        pause = next_at - time.monotonic()
        if pause > 0:
            time.sleep(pause)


def main():
    for seconds, rps, error_rate in phases():
        run(seconds, rps, error_rate)


if __name__ == "__main__":
    main()