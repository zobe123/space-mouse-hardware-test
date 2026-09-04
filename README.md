# SpaceMouse Hardware Test

Linux hardware/function test for 3Dconnexion SpaceMouse devices, aimed at checking used devices.

It checks:

- neutral position / drift on all 6 DoF axes
- min/max travel in both directions on X, Y, Z, Roll, Pitch, Yaw
- button press **and** release events through Linux `evdev`
- a compact seller-friendly TXT report
- a JSON report for documentation

The script does **not** claim to be an official 3Dconnexion diagnostic or calibration tool.

## Example result

```text
3Dconnexion SpaceMouse – Hardwaretest
===========================================
Gerät: SpaceMousePro
Datum: 2026-09-04 08:15:13 CEST
Test: Linux / Raw HID + evdev

6DoF-Sensor – Neutralstellung
--------------------------------
Achse       Mittel       Min       Max    Max|x|   Status
X          +0.0000   +0.0000   +0.0000    0.0000       OK
Y          +0.0000   +0.0000   +0.0000    0.0000       OK
Z          +0.0000   +0.0000   +0.0000    0.0000       OK
Roll       +0.0000   +0.0000   +0.0000    0.0000       OK
Pitch      +0.0000   +0.0000   +0.0000    0.0000       OK
Yaw        +0.0000   +0.0000   +0.0000    0.0000       OK

6DoF-Sensor – Bewegungsbereich
--------------------------------
Achse          Min       Max      Span   Status
X          -0.9200   +0.9500    1.8700       OK
Y          -0.9000   +0.9100    1.8100       OK
Z          -0.9400   +0.9200    1.8600       OK
Roll       -0.8800   +0.9000    1.7800       OK
Pitch      -1.0000   +1.0000    2.0000       OK
Yaw        -0.9100   +0.9300    1.8400       OK

Tasten
--------------------------------
Vom Linux-Gerät gemeldete Tasten: 15
Press + Release erfolgreich:       15/15
Alle gemeldeten Tasten wurden gedrückt und wieder losgelassen: OK

Zusammenfassung
--------------------------------
Neutralstellung / Drift: OK
Alle 6 Achsen, beide Richtungen: OK
Alle Tasten Press + Release: OK
GESAMTERGEBNIS: PASS
```

## Requirements

Python 3 plus:

```bash
pip install pyspacemouse evdev
```

On Arch/SystemRescue it may also be convenient to install system packages:

```bash
pacman -Sy python python-pip hidapi python-evdev
```

Run as root for a quick live/rescue-system test, or configure normal-user access to `/dev/hidraw*` and `/dev/input/event*`.

## Run

```bash
python spacemouse_test.py
```

Optional:

```bash
python spacemouse_test.py \
  --neutral-seconds 30 \
  --range-seconds 40 \
  --button-seconds 60 \
  --output-dir ./reports
```

## Exit codes

- `0`: all configured checks passed
- `2`: one or more checks need review

## Notes

The default neutral warning threshold is `0.05` in PySpaceMouse's normalized axis units. This is a practical test threshold, not a manufacturer specification.

The range test requires at least `-0.10` and `+0.10` on every axis and a total span of at least `0.50`. These are intentionally conservative functional-test thresholds rather than calibration limits.
