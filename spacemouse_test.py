#!/usr/bin/env python3
"""
Interactive SpaceMouse Hardware Test
Linux functional test for 3Dconnexion SpaceMouse devices.

Highlights:
- interactive red/green guidance
- neutral/drift check
- live 12-direction 6DoF checklist
- button press+release verification through evdev
- seller-friendly TXT report + JSON report
- ANSI colors with --no-color fallback

This is an independent function test, not an official 3Dconnexion diagnostic.
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
LABEL = {"x":"X","y":"Y","z":"Z","roll":"Roll","pitch":"Pitch","yaw":"Yaw"}

class C:
    enabled = True
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    @classmethod
    def paint(cls, text, color):
        if not cls.enabled:
            return str(text)
        return f"{color}{text}{cls.RESET}"

def green(s): return C.paint(s, C.GREEN)
def red(s): return C.paint(s, C.RED)
def yellow(s): return C.paint(s, C.YELLOW)
def cyan(s): return C.paint(s, C.CYAN)
def bold(s): return C.paint(s, C.BOLD)

def clear():
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")

def banner(title):
    print("=" * 64)
    print(bold(title))
    print("=" * 64)

def countdown(seconds=3):
    for n in range(seconds, 0, -1):
        print(f"Start in {n} ...", flush=True)
        time.sleep(1)

def axis_values(state):
    return {a: float(getattr(state, a)) for a in AXES}

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

    with_keys = [d for d in candidates if ecodes.EV_KEY in d.capabilities()]
    chosen = max(with_keys or candidates, key=lambda d: len(d.capabilities().get(ecodes.EV_KEY, [])))
    for d in candidates:
        if d is not chosen:
            try: d.close()
            except Exception: pass
    return chosen, None

def key_name(code):
    if ecodes is None:
        return str(code)
    name = ecodes.KEY.get(code)
    if isinstance(name, list):
        name = "/".join(name)
    return name or f"KEY_{code}"

def neutral_test(dev, seconds):
    clear()
    banner("TEST 1/3 – NEUTRAL / DRIFT")
    print()
    print(red("NICHT BERÜHREN"))
    print(f"SpaceMouse auf eine feste Unterlage stellen und {seconds} Sekunden nicht anfassen.")
    print()
    countdown()

    samples = {a: [] for a in AXES}
    start = time.monotonic()
    end = start + seconds
    while time.monotonic() < end:
        state = dev.read()
        vals = axis_values(state)
        for a in AXES:
            samples[a].append(vals[a])

        elapsed = int(time.monotonic() - start)
        width = 28
        fill = int(width * min(1, (time.monotonic()-start)/seconds))
        bar = "#" * fill + "-" * (width-fill)
        print(f"\r[{bar}] {min(elapsed+1,seconds):>2}/{seconds}s", end="", flush=True)
        time.sleep(0.002)
    print("\n")

    result = {}
    for a in AXES:
        s = samples[a] or [0.0]
        result[a] = {
            "mean": statistics.fmean(s),
            "min": min(s),
            "max": max(s),
            "max_abs": max(abs(v) for v in s),
            "rms": math.sqrt(statistics.fmean(v*v for v in s)),
        }
    return result

def show_neutral_result(neutral, threshold):
    print("Ergebnis:")
    for a in AXES:
        d = neutral[a]
        ok = d["max_abs"] < threshold
        status = green("OK") if ok else yellow("PRÜFEN")
        print(f"{LABEL[a]:<6} max|x|={d['max_abs']:.4f}   {status}")
    print()
    print(green("Neutraltest bestanden") if all(neutral[a]["max_abs"] < threshold for a in AXES)
          else yellow("Neutraltest enthält auffällige Werte"))

def range_test(dev, timeout, trigger):
    clear()
    banner("TEST 2/3 – 6DoF BEWEGUNG")
    print()
    print("Führe ALLE Bewegungen mindestens einmal deutlich in BEIDE Richtungen aus.")
    print()
    print("Translation:")
    print("  X:  <- LINKS          RECHTS ->")
    print("  Y:  ^  VOR            ZURÜCK  v")
    print("  Z:  v  DRÜCKEN        HOCHZIEHEN ^")
    print()
    print("Rotation:")
    print("  Roll:   links kippen   <->   rechts kippen")
    print("  Pitch:  vor kippen     <->   zurück kippen")
    print("  Yaw:    links drehen   <->   rechts drehen")
    print()
    print(yellow("Wichtig: Bei Z die Kappe auch aktiv HOCHZIEHEN."))
    print()
    countdown()

    mins = {a: 1.0 for a in AXES}
    maxs = {a: -1.0 for a in AXES}
    seen_neg = {a: False for a in AXES}
    seen_pos = {a: False for a in AXES}

    start = time.monotonic()
    last_render = 0.0

    while True:
        state = dev.read()
        vals = axis_values(state)
        for a in AXES:
            mins[a] = min(mins[a], vals[a])
            maxs[a] = max(maxs[a], vals[a])
            if vals[a] <= -trigger:
                seen_neg[a] = True
            if vals[a] >= trigger:
                seen_pos[a] = True

        now = time.monotonic()
        complete = all(seen_neg[a] and seen_pos[a] for a in AXES)
        expired = now - start >= timeout

        if now - last_render >= 0.08:
            # rewrite a compact live checklist
            print("\033[8A" if sys.stdout.isatty() else "", end="")
            print("Noch zu testen / Status:")
            for a in AXES:
                n = green("OK -") if seen_neg[a] else red("FEHLT -")
                p = green("OK +") if seen_pos[a] else red("FEHLT +")
                print(f"  {LABEL[a]:<6} {n:<18} {p:<18}  live={vals[a]:+0.2f}")
            remaining = max(0, int(timeout - (now-start)))
            print(f"Restzeit: {remaining:2d}s")
            hint = []
            if not seen_pos["z"]:
                hint.append("Z+: Kappe HOCHZIEHEN")
            if not seen_neg["z"]:
                hint.append("Z-: Kappe DRÜCKEN")
            print((yellow("Hinweis: " + " | ".join(hint)) if hint else " " * 50))
            last_render = now

        if complete or expired:
            break
        time.sleep(0.002)

    print()
    result = {}
    for a in AXES:
        result[a] = {
            "min": mins[a],
            "max": maxs[a],
            "span": maxs[a] - mins[a],
            "negative_seen": seen_neg[a],
            "positive_seen": seen_pos[a],
        }
    return result

def button_test(dev, timeout):
    clear()
    banner("TEST 3/3 – TASTEN")
    print()
    if dev is None:
        print(red("Button-Test nicht verfügbar."))
        return {"available": False, "expected_codes": [], "completed": [], "complete": False}

    expected = sorted(int(code) for code in dev.capabilities().get(ecodes.EV_KEY, []))
    print(f"Linux meldet {len(expected)} Tasten-Codes für dieses Gerät.")
    print("Drücke jede Taste einmal vollständig und lasse sie wieder los.")
    print()
    countdown()

    pressed, released = set(), set()
    start = time.monotonic()

    while True:
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
        remaining_codes = [c for c in expected if c not in completed]
        elapsed = time.monotonic() - start

        if sys.stdout.isatty():
            print("\r", end="")
        print(
            f"Vollständig erkannt: {green(str(len(completed)))}/{len(expected)}"
            f" | fehlen: {red(str(len(remaining_codes)))}"
            f" | Restzeit: {max(0,int(timeout-elapsed)):2d}s",
            end="\r" if sys.stdout.isatty() else "\n",
            flush=True,
        )

        if not remaining_codes or elapsed >= timeout:
            break

    print("\n")
    if remaining_codes:
        print(red("Nicht vollständig erkannt:"))
        for code in remaining_codes:
            print(f"  - {code} ({key_name(code)})")
    else:
        print(green("Alle Tasten wurden gedrückt UND wieder losgelassen."))

    return {
        "available": True,
        "expected_codes": expected,
        "pressed": sorted(pressed),
        "released": sorted(released),
        "completed": sorted(completed),
        "complete": not remaining_codes,
    }

def axis_status(d, trigger):
    return "OK" if d["min"] <= -trigger and d["max"] >= trigger else "CHECK"

def build_report(device_name, neutral, ranges, buttons, neutral_warn, trigger):
    neutral_ok = all(neutral[a]["max_abs"] < neutral_warn for a in AXES)
    range_ok = all(axis_status(ranges[a], trigger) == "OK" for a in AXES)
    button_ok = bool(buttons.get("complete"))
    overall = neutral_ok and range_ok and button_ok

    L = []
    L.append("3Dconnexion SpaceMouse – Hardwaretest")
    L.append("="*43)
    L.append(f"Gerät: {device_name}")
    L.append(f"Datum: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    L.append("Test: Linux / Raw HID + evdev")
    L.append("")
    L.append("6DoF-Sensor – Neutralstellung")
    L.append("--------------------------------")
    L.append(f"{'Achse':<8} {'Mittel':>9} {'Min':>9} {'Max':>9} {'Max|x|':>9} {'Status':>8}")
    for a in AXES:
        d=neutral[a]
        st="OK" if d["max_abs"] < neutral_warn else "CHECK"
        L.append(f"{LABEL[a]:<8} {d['mean']:>+9.4f} {d['min']:>+9.4f} {d['max']:>+9.4f} {d['max_abs']:>9.4f} {st:>8}")
    L.append("")
    L.append("6DoF-Sensor – Bewegungsbereich")
    L.append("--------------------------------")
    L.append(f"{'Achse':<8} {'Min':>9} {'Max':>9} {'Span':>9} {'Status':>8}")
    for a in AXES:
        d=ranges[a]
        L.append(f"{LABEL[a]:<8} {d['min']:>+9.4f} {d['max']:>+9.4f} {d['span']:>9.4f} {axis_status(d, trigger):>8}")
    L.append("")
    L.append("Tasten")
    L.append("--------------------------------")
    if buttons.get("available"):
        exp=len(buttons.get("expected_codes", []))
        done=len(buttons.get("completed", []))
        L.append(f"Vom Linux-Gerät gemeldete Tasten: {exp}")
        L.append(f"Press + Release erfolgreich:       {done}/{exp}")
        L.append("Status: " + ("OK" if button_ok else "CHECK"))
    else:
        L.append("Button-Test nicht verfügbar.")
    L.append("")
    L.append("Zusammenfassung")
    L.append("--------------------------------")
    L.append(f"Neutralstellung / Drift: {'PASS' if neutral_ok else 'CHECK'}")
    L.append(f"6 Achsen / 12 Richtungen: {'PASS' if range_ok else 'CHECK'}")
    L.append(f"Tasten Press + Release: {'PASS' if button_ok else 'CHECK'}")
    L.append(f"GESAMTERGEBNIS: {'PASS' if overall else 'CHECK'}")
    L.append("")
    L.append("Hinweis: Unabhängiger Funktionstest; kein offizielles 3Dconnexion-Diagnose- oder Kalibrierprotokoll.")
    return "\n".join(L), overall

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--neutral-seconds", type=int, default=20)
    p.add_argument("--range-seconds", type=int, default=45)
    p.add_argument("--button-seconds", type=int, default=60)
    p.add_argument("--neutral-warn", type=float, default=0.05)
    p.add_argument("--direction-trigger", type=float, default=0.10)
    p.add_argument("--output-dir", default="./reports")
    p.add_argument("--no-color", action="store_true")
    args=p.parse_args()
    C.enabled = (not args.no_color) and sys.stdout.isatty()

    clear()
    banner("3Dconnexion SpaceMouse Hardware Test")
    print()
    print("Dieser Test führt dich Schritt für Schritt durch:")
    print("  1. Neutralstellung / Drift")
    print("  2. 6DoF – alle 12 Richtungen")
    print("  3. Alle Tasten – Press + Release")
    print()

    try:
        connected=pyspacemouse.get_connected_devices()
    except Exception:
        connected=[]

    evdev_dev, evdev_error = find_evdev_spacemouse()
    if evdev_error:
        print(yellow(f"evdev: {evdev_error}"))

    with pyspacemouse.open() as dev:
        device_name = getattr(dev, "name", None) or (connected[0] if connected else "3Dconnexion SpaceMouse")
        neutral = neutral_test(dev, args.neutral_seconds)
        show_neutral_result(neutral, args.neutral_warn)
        input("\nEnter für TEST 2 ...")
        ranges = range_test(dev, args.range_seconds, args.direction_trigger)

    input("\nEnter für TEST 3 ...")
    buttons = button_test(evdev_dev, args.button_seconds)
    if evdev_dev:
        try: evdev_dev.close()
        except Exception: pass

    report, overall = build_report(device_name, neutral, ranges, buttons, args.neutral_warn, args.direction_trigger)

    outdir=Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp=datetime.now().strftime("%Y%m%d-%H%M%S")
    txt=outdir/f"spacemouse-test-{stamp}.txt"
    js=outdir/f"spacemouse-test-{stamp}.json"
    txt.write_text(report+"\n", encoding="utf-8")
    js.write_text(json.dumps({
        "generated_at": datetime.now().astimezone().isoformat(),
        "device": str(device_name),
        "neutral": neutral,
        "range": ranges,
        "buttons": buttons,
        "overall": "PASS" if overall else "CHECK"
    }, indent=2), encoding="utf-8")

    clear()
    banner("GESAMTERGEBNIS")
    print()
    print(report)
    print()
    print(green("HARDWARE TEST PASSED") if overall else yellow("HARDWARE TEST: CHECK"))
    print()
    print(f"TXT-Report:  {txt}")
    print(f"JSON-Report: {js}")
    return 0 if overall else 2

if __name__ == "__main__":
    raise SystemExit(main())
