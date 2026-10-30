"""Event generator / simulator for the Order Supervisor API.

Examples:
    uv run python scripts/simulate.py start --order ORD-1001
    uv run python scripts/simulate.py event <run_id> payment_failed --payload '{"reason": "card_declined"}'
    uv run python scripts/simulate.py scenario <run_id> rough_delivery --delay 10
    uv run python scripts/simulate.py watch <run_id>
"""

import argparse
import json
import sys
import time
from typing import Any

import httpx

SCENARIOS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "happy_path": [
        ("payment_confirmed", {"amount": 2499, "method": "upi"}),
        ("shipment_created", {"carrier": "BlueDart", "tracking_id": "BD123456789IN", "eta_days": 3}),
        ("out_for_delivery", {"courier": "Ravi", "window": "2pm-6pm"}),
        ("delivered", {"signed_by": "Customer"}),
    ],
    "rough_delivery": [
        ("payment_confirmed", {"amount": 2499, "method": "card"}),
        ("shipment_created", {"carrier": "BlueDart", "tracking_id": "BD987654321IN", "eta_days": 3}),
        ("shipment_delayed", {"carrier": "BlueDart", "reason": "weather", "new_eta_days": 6}),
        ("customer_message_received", {"message": "Where is my order? I needed it for a birthday this weekend."}),
    ],
    "payment_trouble": [
        ("payment_failed", {"reason": "card_declined", "attempt": 1}),
        ("no_update_for_n_hours", {"hours": 30}),
        ("payment_confirmed", {"amount": 2499, "method": "upi", "attempt": 2}),
    ],
    "refund": [
        ("delivered", {"signed_by": "Customer"}),
        ("refund_requested", {"reason": "Item arrived damaged", "photos": 2}),
    ],
}

TERMINAL_STATUSES = {"completed", "terminated", "failed"}


def main() -> int:
    args = parse_args()
    with httpx.Client(base_url=args.api, timeout=30) as client:
        try:
            return args.handler(client, args)
        except httpx.HTTPStatusError as exc:
            print(f"API error {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
            return 1
        except httpx.ConnectError:
            print(f"Cannot reach the API at {args.api}. Is the backend running?", file=sys.stderr)
            return 1


def cmd_start(client: httpx.Client, args: argparse.Namespace) -> int:
    body = {
        "supervisor_id": args.supervisor,
        "order_id": args.order,
        "order_context": {"customer": "Asha Rao", "items": ["Running shoes (UK 7)"], "total": "₹2,499", "shipping": "standard"},
        "instructions": args.instruction or [],
    }
    run = _post(client, "/api/runs", body)
    print(f"Started run {run['id']} for order {run['order_id']} (workflow {run['workflow_id']})")
    return 0


def cmd_event(client: httpx.Client, args: argparse.Namespace) -> int:
    payload = json.loads(args.payload) if args.payload else {}
    result = _post(client, f"/api/runs/{args.run_id}/events", {"type": args.type, "payload": payload, "source": "simulator"})
    print(result["message"])
    return 0


def cmd_scenario(client: httpx.Client, args: argparse.Namespace) -> int:
    steps = SCENARIOS[args.name]
    for index, (event_type, payload) in enumerate(steps, start=1):
        _post(client, f"/api/runs/{args.run_id}/events", {"type": event_type, "payload": payload, "source": "simulator"})
        print(f"[{index}/{len(steps)}] sent {event_type}")
        if index < len(steps):
            time.sleep(args.delay)
    return 0


def cmd_watch(client: httpx.Client, args: argparse.Namespace) -> int:
    seen = 0
    while True:
        run = _get(client, f"/api/runs/{args.run_id}")
        for entry in run["timeline"][seen:]:
            print(f"{entry['at'][11:19]}  {entry['kind']:<14} {entry['title']}")
        seen = len(run["timeline"])
        if run["status"] in TERMINAL_STATUSES:
            print(f"\nRun {run['status']}: {run['close_reason']}")
            if run["final_report"]:
                print(json.dumps(run["final_report"], indent=2, ensure_ascii=False))
            return 0
        time.sleep(2)


def _get(client: httpx.Client, path: str) -> dict[str, Any]:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def _post(client: httpx.Client, path: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=body)
    response.raise_for_status()
    return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send simulated order events to the supervisor API.")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    sub = parser.add_subparsers(required=True)

    start = sub.add_parser("start", help="Start a supervisor run for an order")
    start.add_argument("--order", required=True)
    start.add_argument("--supervisor", default="tpl-standard")
    start.add_argument("--instruction", action="append", help="Run-specific instruction (repeatable)")
    start.set_defaults(handler=cmd_start)

    event = sub.add_parser("event", help="Send one event")
    event.add_argument("run_id")
    event.add_argument("type")
    event.add_argument("--payload", help="JSON object")
    event.set_defaults(handler=cmd_event)

    scenario = sub.add_parser("scenario", help="Send a scripted sequence of events")
    scenario.add_argument("run_id")
    scenario.add_argument("name", choices=sorted(SCENARIOS))
    scenario.add_argument("--delay", type=float, default=8, help="Seconds between events")
    scenario.set_defaults(handler=cmd_scenario)

    watch = sub.add_parser("watch", help="Stream a run's timeline until it closes")
    watch.add_argument("run_id")
    watch.set_defaults(handler=cmd_watch)
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
