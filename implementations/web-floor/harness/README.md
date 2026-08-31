# OFP Test Harness Guide

This folder contains the desktop OFP test harness for running Open Floor event tests against one or more agents.

The normal workflow is GUI-first:

- Start the app with Python
- Configure tests in the window
- Run and review results in the summary table and chart popup

## 1. Prerequisites

- Python with Tkinter available
- Optional chart dependencies installed if you want popup charts

Optional chart packages:

```bash
python -m pip install seaborn pandas matplotlib
```

## 2. Launch The Harness

From the `implementations/web-floor` folder:

```bash
python ofp_test.py
```

All testing is configured and executed in the GUI.

## 3. Prepare Agent Targets

You can test agents using:

- Loaded agents from the agent file
- Custom agent URLs (one per line)

The harness starts with an empty loaded-agent list. Use Load Agent File to populate it, or Reset to clear the loaded list again.

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

The agent loader accepts these formats:

- `.json`: a JSON array of objects, or a JSON object with an `agents` array
- `.csv` / `.tsv`: a table with `url` and `conversationalName` or `name` columns
- `.txt`: one URL per line, or `name,url` per line

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
5. Transport is direct only and posts directly to the agent URL.
6. Set Timeout ms.

## 5. Select Agents

- Use Select all loaded agents if desired.
- Or choose specific loaded agents.
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

The harness now sends directly to each target URL.

## 11. Common Troubleshooting

No manifest returned:

- Verify correct target URL, including any required path suffix.
- Example local Verity URL is http://localhost:8768/verity/.
- Confirm agent process is running and listening on the expected port.

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
python ofp_test.py cli run --event getManifests --all-known
```
