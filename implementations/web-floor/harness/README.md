# OFP Test Harness Guide

This folder contains the desktop OFP test harness for running Open Floor event tests against one or more agents.

The normal workflow is GUI-first:

- Start the app with Python
- Configure tests in the window
- Run and review results in the summary table and chart popup

## 1. Prerequisites

- Python environment for implementations/web-floor
- Dependencies for web-floor installed
- Optional chart dependencies installed if you want popup charts

From implementations/web-floor:

```bash
python -m pip install -r requirements.txt
python -m pip install seaborn pandas matplotlib
```

## 2. Launch The Harness

From implementations/web-floor:

```bash
python ofp_test.py
```

All testing is configured and executed in the GUI.

## 3. Prepare Agent Targets

You can test agents using either:

- Known agents (checkbox list)
- Custom agent URLs (one per line)
- Agent file (Load Agent File)

For local Verity, use this endpoint:

- http://localhost:8768/verity/

## 3a. Utterances File Formats

The utterances file loader supports:

- JSON list of strings
- JSON object with an utterances list
- Text/CSV file with one utterance per non-empty line

Examples:

```json
["hello", "check this statement", "summarize this"]
```

```json
{
  "utterances": ["hello", "check this statement", "summarize this"]
}
```

```text
hello
check this statement
summarize this
```

When a file is loaded, each utterance is tested across selected agents (and repeat count).

## 3b. Agent File Format

The agent file should use the same format as `known_agents.json`: a JSON array of objects with `url` and `conversationalName` fields.

```json
[
  {"url": "http://localhost:8768/verity/", "conversationalName": "Verity"},
  {"url": "http://localhost:8082/", "conversationalName": "Erin"}
]
```

## 4. Configure A Test

In the Test Setup panel:

1. Select Event type.
2. For utterance event type, either:
  - fill Utterance directly, or
  - load an utterances file with the Load button.
3. Set Repeat count.
4. Optionally set Expected contains for response text checks.
5. Choose Transport mode (default: direct):
  - direct: posts directly to agent URL
  - gateway: uses Flask proxy endpoint
6. If using gateway, confirm Gateway URL (default usually http://localhost:8090/api/proxy-send).
7. Set Timeout ms.

## 5. Select Agents

- Use Send to all known agents if desired.
- Or choose specific known agents.
- Add any additional custom URLs in the textbox.

## 6. Run, Stop, Clear, Export

Buttons under the setup panel:

- Run: start dispatching requests
- Stop: request cancellation of the current run
- Clear Results: wipe current result rows
- Export Results JSON: save full result payloads for analysis
- Open Summary Chart: open chart popup for counts and timing

Append to existing results controls whether a new run appends or starts fresh.

## 7. Read Results

Results Summary table columns:

- Agent
- Event sent
- Event received
- Result (success, fail, error)
- Duration ms

Selecting a row opens full JSON detail in the lower panel.

## 8. Filter Results

Use the summary filter controls:

- Agent
- Event
- Result

Use Reset Filters to return all filters to All.

## 9. Understand Chart Output

Open Summary Chart shows:

1. Combined success/fail/error count graph
  - X-axis: agent (truncated labels)
  - Y-axis: event counts (integer ticks)
  - Event: color legend
  - Result class: bar pattern (success, fail, error)
2. Processing-time graph
  - X-axis: agent
  - Y-axis: average milliseconds
  - Event: color legend

## 10. Transport Notes

Gateway mode:

- Uses Flask endpoint at api/flask_gateway.py
- Useful for browser-safe routing and unified proxy behavior

Direct mode:

- Sends directly to each target URL
- Useful for local network testing without proxy

## 11. Common Troubleshooting

No manifest returned:

- Verify correct target URL, including any required path suffix.
- Example local Verity URL is http://localhost:8768/verity/.
- Confirm agent process is running and listening on the expected port.
- For gateway mode, verify Flask gateway is running and gateway URL is correct.

All results are error:

- Increase Timeout ms.
- Check agent logs for envelope parsing errors.
- Validate agent endpoint accepts POST OFP envelope payloads.

Chart button errors:

- Install chart packages:

```bash
python -m pip install seaborn pandas matplotlib
```

## 12. Optional Legacy CLI Passthrough

GUI is the primary path. Legacy CLI passthrough remains available for automation:

```bash
python ofp_test.py cli list-agents
python ofp_test.py cli run --event getManifests --all-known --transport gateway
```
