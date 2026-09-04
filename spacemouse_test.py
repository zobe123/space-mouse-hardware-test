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
import platform
import select
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import pyspacemouse
except ImportError:
    pyspacemouse = None


try:
    from evdev import InputDevice, list_devices, ecodes
except ImportError:
    InputDevice = None
    list_devices = None
    ecodes = None

AXES = ("x", "y", "z", "roll", "pitch", "yaw")
LABEL = {"x": "X", "y": "Y", "z": "Z", "roll": "Roll", "pitch": "Pitch", "yaw": "Yaw"}
DEFAULT_NEUTRAL_SECONDS = 20
DEFAULT_RANGE_SECONDS = 45
DEFAULT_BUTTON_SECONDS = 60
DEFAULT_NEUTRAL_WARN = 0.05
DEFAULT_DIRECTION_TRIGGER = 0.10
DEFAULT_DIRECTION_SAMPLES = 3
DEFAULT_RANGE_MIN_SECONDS = 20

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
    if seconds <= 0:
        return
    for n in range(seconds, 0, -1):
        print(f"Start in {n} ...", flush=True)
        time.sleep(1)

def axis_values(state):
    return {a: float(getattr(state, a)) for a in AXES}

def find_evdev_spacemouse(path=None):
    if InputDevice is None:
        return None, "python-evdev ist nicht installiert"

    if path:
        try:
            return InputDevice(path), None
        except Exception as exc:
            return None, f"evdev-Gerät {path!r} kann nicht geöffnet werden: {exc}"

    candidates = []
    errors = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            name = (dev.name or "").lower()
            if "3dconnexion" in name or "spacemouse" in name or "space mouse" in name:
                candidates.append(dev)
            else:
                dev.close()
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    if not candidates:
        detail = f" Fehler beim Lesen: {'; '.join(errors)}" if errors else ""
        return None, "Kein passendes evdev-Gerät gefunden. Prüfe `--list-devices` oder gib mit `--evdev /dev/input/eventX` das Gerät manuell an." + detail

    def key_count(dev):
        return len(dev.capabilities().get(ecodes.EV_KEY, []))

    with_keys = [d for d in candidates if ecodes.EV_KEY in d.capabilities()]
    chosen = max(with_keys or candidates, key=key_count)
    for d in candidates:
        if d is not chosen:
            try:
                d.close()
            except Exception:
                pass
    return chosen, None

def describe_evdev_device(dev):
    if dev is None:
        return None
    return {
        "path": getattr(dev, "path", None),
        "name": getattr(dev, "name", None),
        "phys": getattr(dev, "phys", None),
        "uniq": getattr(dev, "uniq", None),
    }

def list_evdev_candidates():
    if InputDevice is None:
        return [], "python-evdev ist nicht installiert"

    devices = []
    for path in list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            devices.append({
                "path": path,
                "name": dev.name,
                "keys": len(caps.get(ecodes.EV_KEY, [])),
                "axes": len(caps.get(ecodes.EV_ABS, [])),
            })
            dev.close()
        except Exception as exc:
            devices.append({"path": path, "error": str(exc)})
    return devices, None

def key_name(code):
    if ecodes is None:
        return str(code)
    name = ecodes.KEY.get(code)
    if isinstance(name, list):
        name = "/".join(name)
    return name or f"KEY_{code}"

def neutral_test(dev, seconds, countdown_seconds):
    clear()
    banner("TEST 1/3 – NEUTRAL / DRIFT")
    print()
    print(red("NICHT BERÜHREN"))
    print(f"SpaceMouse auf eine feste Unterlage stellen und {seconds} Sekunden nicht anfassen.")
    print()
    countdown(countdown_seconds)

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

def range_test(dev, timeout, min_seconds, trigger, required_samples, countdown_seconds):
    clear()
    banner("TEST 2/3 – 6DoF BEWEGUNG")
    print()
    print("Führe ALLE Bewegungen deutlich in BEIDE Richtungen aus.")
    print(f"Eine Richtung zählt erst ab {required_samples} Messwerten über dem Schwellwert.")
    print(f"Der Test läuft mindestens {min(timeout, min_seconds)} Sekunden, damit echte Maximalwerte sichtbar werden.")
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
    countdown(countdown_seconds)

    mins = {a: 1.0 for a in AXES}
    maxs = {a: -1.0 for a in AXES}
    neg_hits = {a: 0 for a in AXES}
    pos_hits = {a: 0 for a in AXES}
    seen_neg = {a: False for a in AXES}
    seen_pos = {a: False for a in AXES}

    start = time.monotonic()
    last_render = 0.0
    rendered_lines = 0

    while True:
        state = dev.read()
        vals = axis_values(state)
        for a in AXES:
            mins[a] = min(mins[a], vals[a])
            maxs[a] = max(maxs[a], vals[a])
            if vals[a] <= -trigger:
                neg_hits[a] += 1
            if vals[a] >= trigger:
                pos_hits[a] += 1
            seen_neg[a] = neg_hits[a] >= required_samples
            seen_pos[a] = pos_hits[a] >= required_samples

        now = time.monotonic()
        complete = all(seen_neg[a] and seen_pos[a] for a in AXES)
        min_runtime_done = now - start >= min(timeout, min_seconds)
        expired = now - start >= timeout

        render_interval = 0.08 if sys.stdout.isatty() else 2.0
        if now - last_render >= render_interval:
            if sys.stdout.isatty() and rendered_lines:
                print(f"\033[{rendered_lines}A", end="")
            print("Noch zu testen / Status:")
            for a in AXES:
                n = green("OK -") if seen_neg[a] else red("FEHLT -")
                p = green("OK +") if seen_pos[a] else red("FEHLT +")
                hits = f"{neg_hits[a]}/{required_samples} {pos_hits[a]}/{required_samples}"
                print(f"  {LABEL[a]:<6} {n:<18} {p:<18}  live={vals[a]:+0.2f}  hits={hits}")
            remaining = max(0, int(timeout - (now-start)))
            min_remaining = max(0, int(min(timeout, min_seconds) - (now-start)))
            print(f"Restzeit: {remaining:2d}s | Mindestlaufzeit: {min_remaining:2d}s")
            hint = []
            if not seen_pos["z"]:
                hint.append("Z+: Kappe HOCHZIEHEN")
            if not seen_neg["z"]:
                hint.append("Z-: Kappe DRÜCKEN")
            print((yellow("Hinweis: " + " | ".join(hint)) if hint else " " * 50))
            last_render = now
            rendered_lines = 9

        if (complete and min_runtime_done) or expired:
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
            "negative_hits": neg_hits[a],
            "positive_hits": pos_hits[a],
        }
    return result

def button_test(dev, timeout, countdown_seconds, unavailable_reason=None):
    clear()
    banner("TEST 3/3 – TASTEN")
    print()
    if dev is None:
        print(red("Button-Test nicht verfügbar."))
        if unavailable_reason:
            print(yellow(unavailable_reason))
        print("Tipp: `python spacemouse_test.py --list-devices` ausführen und ggf. mit `--evdev /dev/input/eventX` starten.")
        return {
            "available": False,
            "error": unavailable_reason,
            "expected_codes": [],
            "completed": [],
            "complete": False,
        }

    expected = sorted(int(code) for code in dev.capabilities().get(ecodes.EV_KEY, []))
    if not expected:
        print(yellow("Dieses evdev-Gerät meldet keine Tasten-Codes."))
        return {
            "available": True,
            "error": "evdev-Gerät meldet keine Tasten-Codes",
            "expected_codes": [],
            "completed": [],
            "complete": False,
        }

    print(f"Linux meldet {len(expected)} Tasten-Codes für dieses Gerät.")
    print("Drücke jede Taste einmal vollständig und lasse sie wieder los.")
    print()
    countdown(countdown_seconds)

    pressed, released = set(), set()
    start = time.monotonic()

    while True:
        try:
            ready, _, _ = select.select([dev.fd], [], [], 0.15)
            if ready:
                for event in dev.read():
                    if event.type != ecodes.EV_KEY:
                        continue
                    if event.value == 1:
                        pressed.add(int(event.code))
                    elif event.value == 0:
                        released.add(int(event.code))
        except OSError as exc:
            print()
            print(red(f"evdev-Lesefehler: {exc}"))
            break

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

def build_report(device_name, neutral, ranges, buttons, neutral_warn, trigger, system_info):
    neutral_ok = all(neutral[a]["max_abs"] < neutral_warn for a in AXES)
    range_ok = all(axis_status(ranges[a], trigger) == "OK" for a in AXES)
    button_skipped = bool(buttons.get("skipped"))
    button_ok = bool(buttons.get("complete")) and not button_skipped
    overall = neutral_ok and range_ok and button_ok

    L = []
    L.append("3Dconnexion SpaceMouse – Hardwaretest")
    L.append("="*43)
    L.append(f"Gerät: {device_name}")
    L.append(f"Datum: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    L.append("Test: Linux / Raw HID + evdev")
    L.append(f"System: {system_info['platform']}")
    L.append(f"Python: {system_info['python']}")
    L.append(f"Schwellwerte: neutral<{neutral_warn:.4f}, richtung>={trigger:.4f}")
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
    if button_skipped:
        L.append("Button-Test übersprungen.")
        L.append("Status: SKIPPED")
    elif buttons.get("available"):
        exp=len(buttons.get("expected_codes", []))
        done=len(buttons.get("completed", []))
        L.append(f"Vom Linux-Gerät gemeldete Tasten: {exp}")
        L.append(f"Press + Release erfolgreich:       {done}/{exp}")
        L.append("Status: " + ("OK" if button_ok else "CHECK"))
    else:
        L.append("Button-Test nicht verfügbar.")
        if buttons.get("error"):
            L.append(f"Grund: {buttons['error']}")
    L.append("")
    L.append("Zusammenfassung")
    L.append("--------------------------------")
    L.append(f"Neutralstellung / Drift: {'PASS' if neutral_ok else 'CHECK'}")
    L.append(f"6 Achsen / 12 Richtungen: {'PASS' if range_ok else 'CHECK'}")
    if button_skipped:
        L.append("Tasten Press + Release: SKIPPED")
    else:
        L.append(f"Tasten Press + Release: {'PASS' if button_ok else 'CHECK'}")
    L.append(f"GESAMTERGEBNIS: {'PASS' if overall else 'CHECK'}")
    L.append("")
    L.append("Hinweis: Unabhängiger Funktionstest; kein offizielles 3Dconnexion-Diagnose- oder Kalibrierprotokoll.")
    return "\n".join(L), overall

def positive_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("muss eine Ganzzahl sein") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("muss größer als 0 sein")
    return parsed

def non_negative_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("muss eine Ganzzahl sein") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("muss 0 oder größer sein")
    return parsed

def positive_float(value):
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("muss eine Zahl sein") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("muss größer als 0 sein")
    return parsed

def build_parser():
    p = argparse.ArgumentParser(
        description="Interaktiver Linux-Hardwaretest für 3Dconnexion SpaceMouse-Geräte.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--neutral-seconds", type=positive_int, default=DEFAULT_NEUTRAL_SECONDS)
    p.add_argument("--range-seconds", type=positive_int, default=DEFAULT_RANGE_SECONDS)
    p.add_argument("--range-min-seconds", type=positive_int, default=DEFAULT_RANGE_MIN_SECONDS)
    p.add_argument("--button-seconds", type=positive_int, default=DEFAULT_BUTTON_SECONDS)
    p.add_argument("--countdown-seconds", type=non_negative_int, default=3)
    p.add_argument("--neutral-warn", type=positive_float, default=DEFAULT_NEUTRAL_WARN)
    p.add_argument("--direction-trigger", type=positive_float, default=DEFAULT_DIRECTION_TRIGGER)
    p.add_argument("--direction-samples", type=positive_int, default=DEFAULT_DIRECTION_SAMPLES)
    p.add_argument("--output-dir", default="./reports")
    p.add_argument("--evdev", help="evdev-Pfad für den Button-Test, z.B. /dev/input/event12")
    p.add_argument("--skip-buttons", action="store_true", help="Button-Test überspringen")
    p.add_argument("--list-devices", action="store_true", help="erkannte pyspacemouse-/evdev-Geräte ausgeben und beenden")
    p.add_argument("--no-color", action="store_true")
    return p

def print_device_list():
    print("pyspacemouse:")
    if pyspacemouse is None:
        print("  nicht installiert")
    else:
        try:
            devices = pyspacemouse.get_connected_devices()
        except Exception as exc:
            print(f"  Fehler: {exc}")
        else:
            if devices:
                for dev in devices:
                    print(f"  - {dev}")
            else:
                print("  keine Geräte gemeldet")

    print()
    print("evdev:")
    devices, error = list_evdev_candidates()
    if error:
        print(f"  {error}")
        return
    if not devices:
        print("  keine Geräte gemeldet")
        return
    for dev in devices:
        if "error" in dev:
            print(f"  - {dev['path']}: {dev['error']}")
        else:
            print(f"  - {dev['path']}: {dev['name']} (keys={dev['keys']}, axes={dev['axes']})")

def fail(message, code=1):
    sys.stdout.flush()
    print(red(message), file=sys.stderr)
    return code

def main():
    p = build_parser()
    args = p.parse_args()
    C.enabled = (not args.no_color) and sys.stdout.isatty()

    if args.list_devices:
        print_device_list()
        return 0

    if pyspacemouse is None:
        return fail("pyspacemouse ist nicht installiert. Bitte zuerst `pip install -r requirements.txt` ausführen.")

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

    evdev_dev = None
    evdev_error = None
    if not args.skip_buttons:
        evdev_dev, evdev_error = find_evdev_spacemouse(args.evdev)
        if evdev_error:
            print(yellow(f"evdev: {evdev_error}"))
    evdev_info = describe_evdev_device(evdev_dev)

    try:
        with pyspacemouse.open() as dev:
            device_name = getattr(dev, "name", None) or (connected[0] if connected else "3Dconnexion SpaceMouse")
            neutral = neutral_test(dev, args.neutral_seconds, args.countdown_seconds)
            show_neutral_result(neutral, args.neutral_warn)
            input("\nEnter für TEST 2 ...")
            ranges = range_test(
                dev,
                args.range_seconds,
                args.range_min_seconds,
                args.direction_trigger,
                args.direction_samples,
                args.countdown_seconds,
            )

        if args.skip_buttons:
            buttons = {"available": False, "skipped": True, "expected_codes": [], "completed": [], "complete": False}
        else:
            input("\nEnter für TEST 3 ...")
            buttons = button_test(evdev_dev, args.button_seconds, args.countdown_seconds, evdev_error)
    except KeyboardInterrupt:
        print()
        return fail("Abgebrochen.", 130)
    except Exception as exc:
        return fail(f"SpaceMouse konnte nicht geöffnet oder gelesen werden: {exc}")
    finally:
        if evdev_dev:
            try:
                evdev_dev.close()
            except Exception:
                pass

    system_info = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "evdev": evdev_info,
    }
    report, overall = build_report(device_name, neutral, ranges, buttons, args.neutral_warn, args.direction_trigger, system_info)

    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    txt = outdir / f"spacemouse-test-{stamp}.txt"
    js = outdir / f"spacemouse-test-{stamp}.json"
    txt.write_text(report + "\n", encoding="utf-8")
    js.write_text(json.dumps({
        "generated_at": datetime.now().astimezone().isoformat(),
        "device": str(device_name),
        "system": system_info,
        "thresholds": {
            "neutral_warn": args.neutral_warn,
            "direction_trigger": args.direction_trigger,
            "direction_samples": args.direction_samples,
            "range_min_seconds": args.range_min_seconds,
        },
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
