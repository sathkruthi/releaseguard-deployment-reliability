import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

PROMETHEUS = "http://127.0.0.1:19090"
APP = "http://127.0.0.1:18080/work"
DEPENDENCY = "http://127.0.0.1:18081/check"


def http_status(url):
    try:
        with urlopen(url, timeout=2) as response:
            return response.status
    except HTTPError as error:
        error.close()
        return error.code
    except (URLError, TimeoutError, OSError):
        return None


def dependency_health():
    status = http_status(DEPENDENCY)
    return status == 200 if status is not None else None


def query(expression):
    with urlopen(
        PROMETHEUS + "/api/v1/query?" + urlencode({"query": expression}), timeout=3
    ) as response:
        payload = json.load(response)
    if payload.get("status") != "success" or payload["data"]["resultType"] != "vector":
        raise ValueError("Prometheus returned no usable vector")
    result = payload["data"]["result"]
    if any(not math.isfinite(float(item["value"][1])) for item in result):
        raise ValueError("nonfinite Prometheus value")
    return result


def snapshot(revision):
    if revision not in {"v1", "v2", "v3"}:
        raise ValueError("unknown sample revision")
    selector = '{revision="' + revision + '"}'
    live = '((up{job="releaseguard"} == 1) and on(instance) ((time() - timestamp(up{job="releaseguard"})) < 5))'
    ready = query("min(releaseguard_app_ready" + selector + " and on(instance) " + live + ")")
    if not ready:
        raise ValueError("candidate readiness metric missing")
    requests = query("releaseguard_requests_total" + selector + " and on(instance) " + live)
    buckets = query("releaseguard_request_seconds_bucket" + selector + " and on(instance) " + live)
    if not requests or not buckets:
        raise ValueError("candidate counters missing")
    result = {
        "at": time.time(),
        "ready": float(ready[0]["value"][1]) == 1,
        "requests": {},
        "buckets": {},
        "series": {},
        "bucket_series": {},
    }
    for source, dimension, aggregate, series in [
        (requests, "outcome", "requests", "series"),
        (buckets, "le", "buckets", "bucket_series"),
    ]:
        for item in source:
            label = item["metric"][dimension]
            value = float(item["value"][1])
            result[aggregate][label] = result[aggregate].get(label, 0) + value
            result[series][item["metric"]["instance"] + "|" + label] = value
    return result


def wait_snapshot(revision, seconds=20):
    deadline = time.monotonic() + seconds
    last = "candidate metrics unavailable"
    while time.monotonic() < deadline:
        try:
            return snapshot(revision)
        except (ValueError, OSError, URLError, KeyError) as error:
            last = str(error)
            time.sleep(1)
    raise ValueError(last)


def delta(before, after):
    keys = set(before["requests"]) | set(after["requests"])
    differences = {
        key: after["requests"].get(key, 0) - before["requests"].get(key, 0) for key in keys
    }
    buckets = {
        key: after["buckets"].get(key, 0) - before["buckets"].get(key, 0)
        for key in set(before["buckets"]) | set(after["buckets"])
    }
    reset = any(value < 0 for value in [*differences.values(), *buckets.values()])
    for key in ("series", "bucket_series"):
        if key in before or key in after:
            old, new = before.get(key, {}), after.get(key, {})
            reset = (
                reset or set(old) != set(new) or any(new[k] < old[k] for k in set(old) & set(new))
            )
    count = sum(differences.values())
    reset = reset or abs(buckets.get("+Inf", 0) - count) > 0.001
    errors = differences.get("revision", 0) + differences.get("dependency", 0)
    p95 = 0.0
    if count > 0 and not reset:
        threshold = count * 0.95
        for bound in sorted(buckets, key=float):
            if buckets[bound] >= threshold:
                p95 = float(bound)
                break
        else:
            reset = True
    if not math.isfinite(p95):
        reset = True
        p95 = 0
    return {
        "requests": max(count, 0),
        "error_rate": errors / count if count > 0 and not reset else 0,
        "p95_seconds": p95,
        "counter_reset": reset,
        "outcomes": differences,
    }


def observe(revision, minimum):
    before = wait_snapshot(revision)
    responses = []
    for _ in range(minimum + 5):
        responses.append(http_status(APP))
        time.sleep(0.04)
    # Allow the one-second scrape to observe the last request; this is bounded polling evidence.
    time.sleep(2)
    after = wait_snapshot(revision)
    return {
        "before": before,
        "after": after,
        "delta": delta(before, after),
        "responses": responses,
    }
