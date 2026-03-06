# LogPlotterTab — Specification

## Overview

A Python desktop tool for visualizing crazyflie log files (CSV format). The user loads one or more CSV files, selects which signals to plot, and views the resulting subplots in a scrollable panel.

---

## Implementation and design requirements

- **GUI framework:** PyQt6
- **Plotting:** matplotlib
- **Data handling:** pandas

Code should be well modularized and maintainable.

## Performance

- Signal selection changes must feel responsive: There should be no perceptible lag between a checkbox interaction and the UI acknowledging it, even when many signals are selected.

---

## Integration into crazyflie-clients-python

The LogPlotter is a tab embedded in the Crazyflie client. The following constraints come from the existing tab architecture.

**File placement:**
- Python file: `src/cfclient/ui/tabs/LogPlotterTab.py`
- UI layout file: `src/cfclient/ui/tabs/logPlotterTab.ui` (Qt Designer XML format)

**Tab class:**
- Must inherit from `TabToolbox` (from `cfclient.ui.tab_toolbox`) and from a UI class loaded via `PyQt6.uic.loadUiType()`.
- The constructor accepts a single `helper` argument, calls `super().__init__(helper, 'Log Plotter')`, and calls `self.setupUi(self)`.

**Registration:**
- The tab class must be imported and added to the `available` list in `src/cfclient/ui/tabs/__init__.py`.

**Thread safety:**
- Any callbacks from the Crazyflie API must be routed through Qt signals/slots, not called directly on the UI.

**No standalone entry point:**
- The tab has no `main()` function or standalone launch script. Since it operates on offline log files, it does not require connected/disconnected Crazyflie callbacks.

---

## Data Format

### CSV Structure

The standard file format is:

```
Timestamp,ctrltarget.ax,ctrltarget.ay,ctrltarget.pitch,...
119637,0.0,0.0,-0.0,...
119737,0.0,0.0,-0.0,...
```

- First column is named `Timestamp` and contains values in milliseconds.
- All remaining columns are signals.
- Signal names follow a `group.signal` format (e.g. `stateEstimate.x`, `ranging.distance0`). The group is the prefix before the first `.`.

### Loading Rules

1. The timestamp column is named `Timestamp`. Convert its values from milliseconds to seconds.
2. Treat every remaining column as a signal.
3. NaN values in a signal column are not plotted.

### Edge Cases

- **`timestamp_ms` column:** Some files use `timestamp_ms` instead of `Timestamp` as the column name. Handle both; the conversion to seconds is the same.
- **`block` column:** Some files contain a `block` column after the timestamp column. Ignore it entirely. These files have sparse rows — each row only has values for the signals logged in that block; the rest are NaN. The normal NaN-skipping rule applies.
- **Missing or unrecognized timestamp column:** Show an error message to the user and skip the file.
- **Timestamp values not numeric:** Show an error message to the user and skip the file.

---

## Application Layout

The main window is divided into a left panel and a right panel, separated by a resizable divider.

```
┌─────────────────────┬──────────────────────────────────────┐
│  Left panel         │  Right panel                         │
│  (resizable)        │  Plot area (scrollable)              │
│                     │                                      │
│  ┌───────────────┐  │                                      │
│  │  File Picker  │  │                                      │
│  ├───────────────┤  │                                      │
│  │ Signal Picker │  │                                      │
│  ├───────────────┤  │                                      │
│  │  Plot Config  │  │                                      │
│  └───────────────┘  │                                      │
└─────────────────────┴──────────────────────────────────────┘
```

The three subframes in the left panel are stacked vertically and each divider between them is also resizable.

---

## Subframes

### 1. File Picker

**Location:** Top of left panel.

**Controls:**
- **"Add Files…" button** — opens a file dialog in multi-file mode, filtering for `*.csv`. Each invocation can target a different directory. The file picker should default to the project's directory for storing log files.
- **"Remove file" button** - remove file from file list. Removes signals from signal picker and plots.
- **"Clear All" button** — removes all loaded files, resets the signal picker and plots.
- **File list** — shows the base filename of each loaded file. Hovering shows the full path. Files are listed in the order they were added. Adding a file that is already loaded is silently ignored.

**Behavior on file add:**
1. Parse the CSV according to the loading rules.
2. Add the filename to the file list.
3. Populate the signal picker with the new file's signals.
4. Re-render plots for any signals that are already selected.

---

### 2. Signal Picker

**Location:** Middle of left panel.

**Tree structure:**
```
▼ filename_A.csv
    ▼ stateEstimate
        ☐ stateEstimate.x
        ☐ stateEstimate.y
        ☐ stateEstimate.z
    ▼ ranging
        ☐ ranging.distance0
▼ filename_B.csv
    ▼ ctrltarget
        ☐ ctrltarget.pitch
```

- **Top level:** one node per loaded file, showing the basename.
- **Second level:** one node per signal group (prefix before the first `.`). Signals without a `.` in their name go under a group named `(ungrouped)`.
- **Third level (leaf):** individual signal checkboxes, labeled with the full column name.
- All nodes start unchecked and expanded.
- Checking/unchecking a group or file node cascades to all its children.
- A parent node shows a partial state when only some of its children are checked.

**Behavior on checkbox change:** Re-render the plot area.

---

### 3. Plot Configuration

**Location:** Bottom of left panel.

| Setting | Type | Default | Description |
|---|---|---|---|
| Start time from zero | Checkbox | On | If on, subtract the global minimum timestamp (across all loaded files) from all time values before plotting, so t=0 is the earliest data point in any file. |
| Link X axes | Checkbox | On | If on, all subplots share the same x-axis; panning or zooming one plot updates all others. |
| Grid | Checkbox | On | Show grid lines. |

**Behavior on change:** Re-render the plot area.

---

### 4. Plot Area

**Location:** Right panel. Scrollable vertically.

**Layout:**
- One subplot per selected (file, signal) pair.
- All subplots in a single column, stacked vertically.
- The plot area grows in height with the number of subplots; a scrollbar appears when they exceed the visible area.

**Tools:**
- All tools available in the matplotlib plot tool (e.g. zoom, save file)

**Each subplot:**
- **Title:** `<basename>:<signal_name>` (e.g. `log_0.csv:stateEstimate.x`)
- **X label:** `Time (s)`
- **Y label:** `<signal_name>`
- **Data:** a line plot of the signal's values over time, with NaN rows dropped.

**Subplot ordering:**
- Primary: file order (order files were added).
- Secondary: signal order within the tree (group order, then signal order within group).

**Empty state:** When no signals are selected, the plot area shows the message `"No signals selected"`.

**Re-render:** On any change (signal selection, config, file add/remove), rebuild all plots from scratch.

---

## Additional Edge Cases

- **File with only NaN for a selected signal:** show the subplot with title and labels but no data line.
- **Duplicate basenames from different paths:** append a counter suffix in the UI: `log.csv`, `log.csv (2)`, etc. The full path is used internally to distinguish files.

---

## Dependencies

```
PyQt6>=6.7
matplotlib>=3.7
pandas>=2.0
```

These should be added to the projects `pyproject.toml`