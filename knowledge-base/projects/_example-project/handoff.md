# _example-project -- handoff

This is what a project's living memory looks like. Copy the shape, delete this
folder once you have real projects. Entries are APPENDED, newest at the bottom,
each dated and tagged with who wrote it. Never rewrite history here; correct it
with a new dated entry.

## 2026-01-15 -- created (Claude Code). Code: `code/example-project/` (own repo, hooks installed)
A temperature logger for the garage: ESP32 + a DS18B20 probe, posting to a
local dashboard every 5 minutes.

- Wiring: probe data on GPIO 4 with a 4.7k pull-up to 3V3.
- Firmware compiles (`pio run`). **NOT flashed, NOT on hardware.**
- Assumed, not measured: the probe cable length (~3 m) is fine for one-wire
  at 4.7k. Owner to confirm.

## 2026-01-16 -- first flash (owner's report)
- Flashed; readings arrive. Owner said the probe reads ~1.5 C high vs a
  kitchen thermometer (owner's comparison, one sample).
- Next: a two-point calibration (ice water, boiling) before trusting absolute
  values; relative trends are usable now.

## Status
Working on hardware for relative trends. Absolute accuracy unverified.
