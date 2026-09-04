#!/usr/bin/env python3
"""
SpaceMouse Hardware Test
Linux hardware/function test for 3Dconnexion SpaceMouse devices.

Tests:
  1) Neutral position / drift on all 6 axes
  2) Min/max range in both directions for all 6 axes
  3) Linux evdev button press + release events
  4) Generates a compact seller-friendly TXT report plus JSON

This is an independent functional test, not an official 3Dconnexion diagnostic.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import select
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import pyspacemouse

try:
    from evdev import InputDevice, list_devices, ecodes
except ImportError:
    InputDevice = None
    list_devices = None
    ecodes = None


AXES = ("x", "y", "z", "roll", "pitch", "yaw")
AXIS_LABELS = {
    "x": "X",
    "y": "Y",
    "z": "Z",
    "roll": "Roll",
    "pitch": "Pitch",
    "yaw": "Yaw",
}

DEFAULT_EXPECTED_BUTTONS = 15


def axis_values(state):
    return {a: float(getattr(state, a)) for a in AXES}


def countdown(text, seconds=3):
    print()
    print(text)
    for n in range(seconds, 0, -1):
        print(f"Start in {n} ...", flush=True)
        time.sleep(1)


def find_evdev_spacemouse():
    if InputDevice is None:
        return None, "python-evdev ist nicht installiert"

    candidates = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            name = (dev.name or "").lower()
            if "3dconnexion" in name or "spacemouse" in name or "space mouse" in name:
                candidates.append(dev)
            else:
                dev.close()
        except Exception:
            pass

    if not candidates:
        return None, "Kein passendes evdev-Gerät gefunden"

    # Prefer the candidate that actually exposes EV_KEY capabilities.
    for dev in candidates:
        caps = dev.capabilities()
        if ecodes.EV_KEY in caps and len(caps[ecodes.EV_KEY]) > 0:
            for other in candidates:
                if other is not dev:
                    try:
                        other.close()
                    except Exception:
                        pass
            return dev, None

    dev = candidates[0]
    for other in candidates[1:]:
        try:
            other.close()
        except Exception:
            pass
    return dev, "Gerät gefunden, aber keine EV_KEY-Capabilities sichtbar"


def get_button_capabilities(dev):
    if dev is None or ecodes is None:
        return []
    caps = dev.capabilities()
    return sorted(int(code) for code in caps.get(ecodes.EV_KEY, []))


def key_name(code):
    if ecodes is None:
        return str(code)
    name = ecodes.KEY.get(code)
    if isinstance(name, list):
        name = "/".join(name)
    return name or f"KEY_{code}"


def test_neutral(dev, duration):
    samples = {a: [] for a in AXES}
    end = time.monotonic() + duration

    while time.monotonic() < end:
        state = dev.read()
        vals = axis_values(state)
        for a in AXES:
            samples[a].append(vals[a])
        time.sleep(0.002)

    out = {}
    for a in AXES:
        s = samples[a] or [0.0]
        out[a] = {
            "mean": statistics.fmean(s),
            "min": min(s),
            "max": max(s),
            "max_abs": max(abs(v) for v in s),
            "rms": math.sqrt(statistics.fmean(v * v for v in s)),
        }
    return out


def test_range(dev, duration):
    mins = {a: 1.0 for a in AXES}
    maxs = {a: -1.0 for a in AXES}

    end = time.monotonic() + duration
    last_print = 0.0

    while time.monotonic() < end:
        state = dev.read()
        vals = axis_values(state)

        for a in AXES:
            mins[a] = min(mins[a], vals[a])
            maxs[a] = max(maxs[a], vals[a])

        now = time.monotonic()
        if now - last_print >= 0.08:
            live = "  ".join(f"{AXIS_LABELS[a]} {vals[a]:+0.2f}" for a in AXES)
            print("\r" + live + " " * 8, end="", flush=True)
            last_print = now

        time.sleep(0.002)

    print()

    out = {}
    for a in AXES:
        lo, hi = mins[a], maxs[a]
        out[a] = {
            "min": lo,
            "max": hi,
            "span": hi - lo,
            "negative_seen": lo <= -0.10,
            "positive_seen": hi >= 0.10,
        }
    return out


def test_buttons(dev, expected_codes, duration):
    if dev is None:
        return {
            "available": False,
            "expected_codes": [],
            "pressed": [],
            "released": [],
            "complete": False,
        }

    pressed = set()
    released = set()

    print()
    print("Drücke jetzt JEDE Taste mindestens einmal und lasse sie wieder los.")
    print("Der Fortschritt wird live angezeigt.")
    print()

    end = time.monotonic() + duration

    while time.monotonic() < end:
        remaining = max(0, int(end - time.monotonic()))
        ready, _, _ = select.select([dev.fd], [], [], 0.15)

        if ready:
            for event in dev.read():
                if event.type != ecodes.EV_KEY:
                    continue
                if event.value == 1:
                    pressed.add(int(event.code))
                elif event.value == 0:
                    released.add(int(event.code))

        completed = pressed & released
        expected_count = len(expected_codes) if expected_codes else DEFAULT_EXPECTED_BUTTONS
        print(
            f"\rButtons vollständig erkannt: {len(completed)}/{expected_count} "
            f"  Restzeit: {remaining:2d}s",
            end="",
            flush=True,
        )

        if expected_codes and set(expected_codes).issubset(completed):
            break

    print()

    completed = pressed & released
    complete = bool(expected_codes) and set(expected_codes).issubset(completed)

    return {
        "available": True,
        "expected_codes": expected_codes,
        "pressed": sorted(pressed),
        "released": sorted(released),
        "completed": sorted(completed),
        "complete": complete,
    }


def axis_range_status(data):
    if data["min"] > -0.10 or data["max"] < 0.10:
        return "FAIL"
    if data["span"] < 0.50:
        return "CHECK"
    return "OK"


def neutral_status(data, warn=0.05):
    return "OK" if data["max_abs"] < warn else "CHECK"


def fmt_button(code):
    return f"{code} ({key_name(code)})"


def build_report(device_name, neutral, ranges, buttons, neutral_warn):
    overall_axis = all(axis_range_status(ranges[a]) == "OK" for a in AXES)
    overall_neutral = all(neutral_status(neutral[a], neutral_warn) == "OK" for a in AXES)
    overall_buttons = bool(buttons.get("complete"))

    overall = overall_axis and overall_neutral and overall_buttons

    lines = []
    lines.append("3Dconnexion SpaceMouse – Hardwaretest")
    lines.append("=" * 43)
    lines.append(f"Gerät: {device_name}")
    lines.append(f"Datum: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append("Test: Linux / Raw HID + evdev")
    lines.append("")

    lines.append("6DoF-Sensor – Neutralstellung")
    lines.append("--------------------------------")
    lines.append(f"{'Achse':<8} {'Mittel':>9} {'Min':>9} {'Max':>9} {'Max|x|':>9} {'Status':>8}")
    for a in AXES:
        d = neutral[a]
        lines.append(
            f"{AXIS_LABELS[a]:<8} "
            f"{d['mean']:>+9.4f} {d['min']:>+9.4f} {d['max']:>+9.4f} "
            f"{d['max_abs']:>9.4f} {neutral_status(d, neutral_warn):>8}"
        )

    lines.append("")
    lines.append("6DoF-Sensor – Bewegungsbereich")
    lines.append("--------------------------------")
    lines.append(f"{'Achse':<8} {'Min':>9} {'Max':>9} {'Span':>9} {'Status':>8}")
    for a in AXES:
        d = ranges[a]
        lines.append(
            f"{AXIS_LABELS[a]:<8} "
            f"{d['min']:>+9.4f} {d['max']:>+9.4f} {d['span']:>9.4f} "
            f"{axis_range_status(d):>8}"
        )

    lines.append("")
    lines.append("Tasten")
    lines.append("--------------------------------")
    if buttons.get("available"):
        expected = buttons.get("expected_codes", [])
        completed = buttons.get("completed", [])
        lines.append(f"Vom Linux-Gerät gemeldete Tasten: {len(expected)}")
        lines.append(f"Press + Release erfolgreich:       {len(completed)}/{len(expected)}")
        missing = sorted(set(expected) - set(completed))
        if missing:
            lines.append("Nicht vollständig erkannt:")
            for code in missing:
                lines.append(f"  - {fmt_button(code)}")
        else:
            lines.append("Alle gemeldeten Tasten wurden gedrückt und wieder losgelassen: OK")
    else:
        lines.append("Button-Test nicht verfügbar.")

    lines.append("")
    lines.append("Zusammenfassung")
    lines.append("--------------------------------")
    lines.append(f"Neutralstellung / Drift: {'OK' if overall_neutral else 'PRÜFEN'}")
    lines.append(f"Alle 6 Achsen, beide Richtungen: {'OK' if overall_axis else 'PRÜFEN'}")
    lines.append(f"Alle Tasten Press + Release: {'OK' if overall_buttons else 'PRÜFEN'}")
    lines.append(f"GESAMTERGEBNIS: {'PASS' if overall else 'CHECK'}")
    lines.append("")
    lines.append(
        "Hinweis: Unabhängiger Funktionstest; kein offizielles "
        "3Dconnexion-Diagnose- oder Kalibrierprotokoll."
    )
    return "\n".join(lines), overall


def main():
    ap = argparse.ArgumentParser(description="SpaceMouse Linux Hardware Test")
    ap.add_argument("--neutral-seconds", type=int, default=20)
    ap.add_argument("--range-seconds", type=int, default=30)
    ap.add_argument("--button-seconds", type=int, default=45)
    ap.add_argument("--neutral-warn", type=float, default=0.05)
    ap.add_argument("--output-dir", default=".")
    args = ap.parse_args()

    print("SpaceMouse Hardware Test")
    print("========================")
    print()

    try:
        connected = pyspacemouse.get_connected_devices()
    except Exception:
        connected = []

    print("PySpaceMouse-Geräte:", connected or "keine Liste verfügbar")

    evdev_dev, evdev_warning = find_evdev_spacemouse()
    expected_codes = get_button_capabilities(evdev_dev)

    if evdev_dev:
        print(f"evdev: {evdev_dev.path} – {evdev_dev.name}")
        print(f"evdev-Tasten-Capabilities: {len(expected_codes)}")
    elif evdev_warning:
        print("evdev:", evdev_warning)

    countdown(
        f"TEST 1/3 – Neutralstellung ({args.neutral_seconds}s)\n"
        "SpaceMouse auf eine feste Unterlage stellen und NICHT berühren.",
        3,
    )

    with pyspacemouse.open() as dev:
        device_name = getattr(dev, "name", None) or (
            connected[0] if connected else "3Dconnexion SpaceMouse"
        )

        neutral = test_neutral(dev, args.neutral_seconds)

        print()
        print("Neutraltest abgeschlossen.")
        for a in AXES:
            d = neutral[a]
            print(
                f"  {AXIS_LABELS[a]:<6} mean={d['mean']:+.4f} "
                f"min={d['min']:+.4f} max={d['max']:+.4f} "
                f"max|x|={d['max_abs']:.4f}"
            )

        countdown(
            f"TEST 2/3 – 6DoF-Bereich ({args.range_seconds}s)\n"
            "Jetzt jede der 6 Bewegungen in BEIDE Richtungen mehrfach deutlich auslenken:\n"
            "X links/rechts, Y vor/zurück, Z hoch/runter,\n"
            "Roll, Pitch und Yaw jeweils in beide Richtungen.",
            3,
        )

        ranges = test_range(dev, args.range_seconds)

    print()
    print("Achsentest abgeschlossen.")
    for a in AXES:
        d = ranges[a]
        print(
            f"  {AXIS_LABELS[a]:<6} min={d['min']:+.4f} "
            f"max={d['max']:+.4f} span={d['span']:.4f} "
            f"{axis_range_status(d)}"
        )

    if evdev_dev:
        countdown(
            f"TEST 3/3 – Tasten ({args.button_seconds}s)\n"
            "Jede Taste mindestens einmal vollständig drücken und loslassen.",
            3,
        )
        buttons = test_buttons(evdev_dev, expected_codes, args.button_seconds)
        try:
            evdev_dev.close()
        except Exception:
            pass
    else:
        buttons = {
            "available": False,
            "expected_codes": [],
            "pressed": [],
            "released": [],
            "completed": [],
            "complete": False,
        }

    report, overall = build_report(
        str(device_name), neutral, ranges, buttons, args.neutral_warn
    )

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    txt_path = outdir / f"spacemouse-test-{stamp}.txt"
    json_path = outdir / f"spacemouse-test-{stamp}.json"

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "device": str(device_name),
        "platform": platform.platform(),
        "neutral_warn_threshold": args.neutral_warn,
        "neutral": neutral,
        "range": ranges,
        "buttons": buttons,
        "overall": "PASS" if overall else "CHECK",
    }

    txt_path.write_text(report + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print()
    print(report)
    print()
    print(f"TXT-Report:  {txt_path}")
    print(f"JSON-Report: {json_path}")

    return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(main())
