#!/usr/bin/env python3
import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


KNOWN_AGENTS_PATH = Path(__file__).with_name("known_agents.json")
EVENT_CHOICES = ("getManifests", "invite", "utterance")


@dataclass
class DispatchResult:
    agent_url: str
    agent_name: str
    event_sent: str
    event_received: str
    result: str
    status_code: int | None
    duration_ms: int
    error: str | None
    response: Any
    request_payload: dict[str, Any]


def load_known_agents() -> list[dict[str, str]]:
    with KNOWN_AGENTS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("known_agents.json must contain a list")
    return data


def clean_url(url: str) -> str:
    return (url or "").strip()


def load_scenario(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    scenario_path = Path(path)
    with scenario_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Scenario file must contain a JSON object")
    return data


def pick_targets(args: argparse.Namespace, scenario: dict[str, Any], known_agents: list[dict[str, str]]) -> list[tuple[str, str]]:
    name_to_url = {}
    for agent in known_agents:
        url = clean_url(agent.get("url", ""))
        if not url:
            continue
        name = (agent.get("conversationalName") or "").strip()
        if name:
            name_to_url[name.lower()] = url

    explicit_urls: list[str] = []
    explicit_urls.extend(clean_url(u) for u in (scenario.get("agents") or []))
    explicit_urls.extend(clean_url(u) for u in (args.agent or []))

    for known_name in (args.agent_name or []):
        found = name_to_url.get(known_name.lower().strip())
        if not found:
            raise ValueError(f"Unknown agent name: {known_name}")
        explicit_urls.append(found)

    if args.all_known:
        explicit_urls.extend(clean_url(agent.get("url", "")) for agent in known_agents)

    dedup: list[str] = []
    seen = set()
    for url in explicit_urls:
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        dedup.append(url)

    if not dedup:
        raise ValueError("No target agents selected. Use --agent, --agent-name, or --all-known.")

    result: list[tuple[str, str]] = []
    for url in dedup:
        matching = next((a for a in known_agents if clean_url(a.get("url", "")) == url), None)
        name = (matching or {}).get("conversationalName") or url
        result.append((url, name))
    return result


def build_payload(event_type: str, target_url: str, utterance: str, client_uri: str, client_url: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "openFloor": {
            "conversation": {
                "id": str(uuid.uuid4()),
                "conversants": []
            },
            "sender": {
                "speakerUri": client_uri,
                "serviceUrl": client_url
            },
            "events": []
        }
    }

    if event_type in ("getManifests", "invite"):
        payload["openFloor"]["events"].append({
            "eventType": event_type,
            "to": {"serviceUrl": target_url}
        })
    elif event_type == "utterance":
        payload["openFloor"]["events"].append({
            "eventType": "utterance",
            "parameters": {
                "dialogEvent": {
                    "speakerUri": client_uri,
                    "features": {
                        "text": {
                            "mimeType": "text/plain",
                            "tokens": [{"value": utterance}]
                        }
                    }
                }
            }
        })
    else:
        raise ValueError(f"Unsupported event type: {event_type}")

    return payload


def http_post_json(url: str, body: dict[str, Any], timeout_ms: int) -> tuple[int, str, Any, str]:
    request_body = json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=request_body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "web-floor-cli-harness/0.1",
        },
    )

    timeout = max(0.1, timeout_ms / 1000.0)

    try:
        with urlopen(req, timeout=timeout) as response:
            raw_text = response.read().decode("utf-8", errors="replace")
            status = int(response.getcode())
            reason = getattr(response, "reason", "") or ""
    except HTTPError as error:
        raw_text = error.read().decode("utf-8", errors="replace")
        status = int(error.code)
        reason = error.reason or ""
    except URLError as error:
        raise RuntimeError(str(error.reason)) from error

    try:
        parsed = json.loads(raw_text) if raw_text else None
    except json.JSONDecodeError:
        parsed = None

    return status, reason, parsed, raw_text


def send_one(target_url: str, payload: dict[str, Any], timeout_ms: int) -> tuple[bool, int | None, str | None, Any, str | None]:
    status, reason, parsed, raw_text = http_post_json(target_url, payload, timeout_ms)
    if not (200 <= status < 300):
        return False, status, f"HTTP {status} {reason}".strip(), parsed or raw_text, None
    return True, status, None, parsed if parsed is not None else raw_text, None


def classify_received(response: Any, is_error: bool) -> str:
    if is_error:
        return "-"
    if not isinstance(response, dict):
        return "(response)" if response is not None else "-"

    events = None
    if isinstance(response.get("openFloor"), dict):
        events = response["openFloor"].get("events")
    if events is None:
        events = response.get("events")

    if isinstance(events, list):
        if not events:
            return "(response [])"
        labels: list[str] = []
        for event in events:
            if isinstance(event, dict) and event.get("eventType"):
                labels.append(str(event["eventType"]))
            else:
                labels.append("(unknown)")
        return ", ".join(labels)

    return "(response)"


def run_harness(args: argparse.Namespace) -> int:
    scenario = load_scenario(args.scenario)
    known_agents = load_known_agents()

    event_type = scenario.get("event") or args.event
    if event_type not in EVENT_CHOICES:
        raise ValueError(f"--event is required and must be one of: {', '.join(EVENT_CHOICES)}")

    utterance = str(scenario.get("utterance") or args.utterance or "")
    if event_type == "utterance" and not utterance:
        raise ValueError("--utterance is required when --event utterance")

    repeat = int(scenario.get("repeat") or args.repeat)
    if repeat < 1:
        raise ValueError("--repeat must be >= 1")

    expected_contains = str(scenario.get("expected_contains") or args.expected_contains or "")
    timeout_ms = int(scenario.get("timeout_ms") or args.timeout_ms)
    client_uri = str(scenario.get("client_uri") or args.client_uri)
    client_url = str(scenario.get("client_url") or args.client_url)

    targets = pick_targets(args, scenario, known_agents)

    dispatch_results: list[DispatchResult] = []

    total = len(targets) * repeat
    completed = 0

    print(f"Running {total} dispatches: event={event_type}, transport=direct")

    for agent_url, agent_name in targets:
        for _ in range(repeat):
            payload = build_payload(event_type, agent_url, utterance, client_uri, client_url)
            started = time.perf_counter()
            try:
                ok, status_code, error, response, _ = send_one(
                    target_url=agent_url,
                    payload=payload,
                    timeout_ms=timeout_ms,
                )
            except Exception as exc:
                ok = False
                status_code = None
                error = str(exc)
                response = None

            duration_ms = int((time.perf_counter() - started) * 1000)

            text_for_expectation = json.dumps(response, ensure_ascii=False) if not isinstance(response, str) else response
            failed_expectation = bool(expected_contains) and (expected_contains.lower() not in text_for_expectation.lower())

            if not ok:
                result = "error"
            elif failed_expectation:
                result = "fail"
            else:
                result = "success"

            event_received = classify_received(response, is_error=(result == "error"))

            dispatch_results.append(
                DispatchResult(
                    agent_url=agent_url,
                    agent_name=agent_name,
                    event_sent=event_type,
                    event_received=event_received,
                    result=result,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    error=error,
                    response=response,
                    request_payload=payload,
                )
            )

            completed += 1
            print(f"[{completed}/{total}] {agent_name}: {result}")

    print_table(dispatch_results)

    success_count = sum(1 for r in dispatch_results if r.result == "success")
    fail_count = sum(1 for r in dispatch_results if r.result == "fail")
    error_count = sum(1 for r in dispatch_results if r.result == "error")

    print("\nSummary:")
    print(f"  success: {success_count}")
    print(f"  fail:    {fail_count}")
    print(f"  error:   {error_count}")
    print(f"  total:   {len(dispatch_results)}")

    if args.out:
        artifact = {
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event_type,
            "transport": "direct",
            "summary": {
                "success": success_count,
                "fail": fail_count,
                "error": error_count,
                "total": len(dispatch_results),
            },
            "results": [asdict(r) for r in dispatch_results],
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nSaved artifact: {out_path}")

    if error_count > 0:
        return 2
    if fail_count > 0:
        return 1
    return 0


def print_table(rows: list[DispatchResult]) -> None:
    if not rows:
        print("No results.")
        return

    headers = ["Agent", "Event sent", "Event received", "Result", "Duration ms"]
    table_rows = [
        [
            r.agent_name,
            r.event_sent,
            r.event_received,
            r.result,
            str(r.duration_ms),
        ]
        for r in rows
    ]

    widths = [len(h) for h in headers]
    for row in table_rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def fmt_line(values: list[str]) -> str:
        return " | ".join(v.ljust(widths[i]) for i, v in enumerate(values))

    sep = "-+-".join("-" * w for w in widths)
    print("\n" + fmt_line(headers))
    print(sep)
    for row in table_rows:
        print(fmt_line(row))


def list_agents() -> int:
    known_agents = load_known_agents()
    print("Known agents:")
    for idx, agent in enumerate(known_agents, start=1):
        url = clean_url(agent.get("url", ""))
        name = (agent.get("conversationalName") or "").strip()
        display = name if name else "(unnamed)"
        print(f"{idx:2d}. {display} -> {url}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Independent CLI test harness for web-floor Open Floor agents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a test dispatch against one or more agents")
    run_parser.add_argument("--event", choices=EVENT_CHOICES, help="Event type to send")
    run_parser.add_argument("--utterance", default="", help="Utterance text (required for event=utterance)")
    run_parser.add_argument("--agent", action="append", default=[], help="Target agent URL (repeatable)")
    run_parser.add_argument("--agent-name", action="append", default=[], help="Known agent conversationalName (repeatable)")
    run_parser.add_argument("--all-known", action="store_true", help="Include all known agents from harness/known_agents.json")
    run_parser.add_argument("--repeat", type=int, default=1, help="Repeat count per agent")
    run_parser.add_argument("--expected-contains", default="", help="Mark as fail if response does not contain this text")
    run_parser.add_argument("--timeout-ms", type=int, default=10000, help="Timeout per request in milliseconds")
    run_parser.add_argument("--client-uri", default="openFloor://cli-test-harness", help="Sender speakerUri in envelope")
    run_parser.add_argument("--client-url", default="cli://test-harness", help="Sender serviceUrl in envelope")
    run_parser.add_argument("--scenario", default="", help="Path to scenario JSON file")
    run_parser.add_argument("--out", default="", help="Write full run artifact JSON to this file")

    subparsers.add_parser("list-agents", help="List known agents from harness/known_agents.json")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "list-agents":
            return list_agents()
        if args.command == "run":
            return run_harness(args)
        parser.error("Unknown command")
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
