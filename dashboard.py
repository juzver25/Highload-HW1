import base64
import json
import os
from urllib.request import Request, urlopen

DATASOURCE = {"type": "prometheus", "uid": "prometheus"}


def get_json(url):
    with urlopen(url) as response:
        return json.load(response)


def post_json(url, payload, user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = Request(url, data=json.dumps(payload).encode(), method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Basic {token}")
    with urlopen(request) as response:
        return json.load(response)


def variable(name, label, label_name):
    query = f"label_values(http_requests_total, {label_name})"
    return {
        "name": name,
        "label": label,
        "type": "query",
        "datasource": DATASOURCE,
        "definition": query,
        "query": {
            "qryType": 1,
            "query": query,
            "refId": "PrometheusVariableQueryEditor-VariableQuery",
        },
        "refresh": 1,
        "includeAll": True,
        "allValue": ".*",
        "multi": True,
        "sort": 1,
    }


def panel(panel_id, title, targets, x, y, unit):
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "datasource": DATASOURCE,
        "gridPos": {"h": 8, "w": 8, "x": x, "y": y},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "targets": [
            {"expr": expr, "legendFormat": legend, "refId": ref}
            for ref, legend, expr in targets
        ],
    }


def queries(handler):
    selector = f'handler="{handler}", datacenter=~"$datacenter", pod=~"$pod"'

    def latency(q):
        return (
            f"histogram_quantile({q}, sum by (le) "
            f"(rate(http_request_duration_seconds_bucket{{{selector}}}[5m])))"
        )

    rps = f"sum(rate(http_requests_total{{{selector}}}[1m]))"
    errors = (
        "sum by (status) (rate(http_requests_total{"
        f'{selector}, status=~"4..|5.."'
        "}[1m]))"
    )
    return latency, rps, errors


def build(handlers):
    panels = []
    panel_id = 1
    for row, handler in enumerate(handlers):
        latency, rps, errors = queries(handler)
        y = row * 8
        panels.append(panel(panel_id, f"{handler} latency", [
            ("A", "p50", latency("0.5")),
            ("B", "p95", latency("0.95")),
            ("C", "p99", latency("0.99")),
        ], 0, y, "s"))
        panels.append(panel(panel_id + 1, f"{handler} rps", [
            ("A", "rps", rps),
        ], 8, y, "reqps"))
        panels.append(panel(panel_id + 2, f"{handler} errors", [
            ("A", "{{status}}", errors),
        ], 16, y, "reqps"))
        panel_id += 3
    return {
        "overwrite": True,
        "dashboard": {
            "uid": "items-handlers",
            "title": "Items handlers",
            "editable": False,
            "refresh": "5s",
            "schemaVersion": 39,
            "time": {"from": "now-15m", "to": "now"},
            "templating": {
                "list": [
                    variable("datacenter", "Datacenter", "datacenter"),
                    variable("pod", "Pod", "pod"),
                ]
            },
            "panels": panels,
        },
    }


def main():
    app_url = os.environ["APP_URL"].rstrip("/")
    grafana_url = os.environ["GRAFANA_URL"].rstrip("/")
    handlers = get_json(f"{app_url}/handlers")
    payload = build(handlers)
    result = post_json(
        f"{grafana_url}/api/dashboards/db",
        payload,
        os.environ["GRAFANA_ADMIN_USER"],
        os.environ["GRAFANA_ADMIN_PASSWORD"],
    )
    print(result)


if __name__ == "__main__":
    main()