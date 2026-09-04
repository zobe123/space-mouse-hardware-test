# SpaceMouse Hardware Test

Interaktiver Linux-Hardwaretest für 3Dconnexion SpaceMouse-Geräte.

## Was wird geprüft?

- Neutralstellung / Drift aller 6 Achsen
- alle 12 Bewegungsrichtungen:
  - X links / rechts
  - Y vor / zurück
  - Z drücken / **hochziehen**
  - Roll links / rechts
  - Pitch vor / zurück
  - Yaw links / rechts
- alle Tasten über Linux `evdev`
- Press **und** Release jeder Taste
- TXT-Report
- JSON-Report für technische Dokumentation

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Start

```bash
python spacemouse_test.py
```

Optional:

```bash
python spacemouse_test.py \
  --neutral-seconds 30 \
  --range-seconds 60 \
  --range-min-seconds 20 \
  --direction-samples 3 \
  --peak-target 0.90 \
  --button-seconds 90
```

Geräte anzeigen:

```bash
python spacemouse_test.py --list-devices
```

Falls der Button-Test das falsche `evdev`-Gerät erwischt:

```bash
python spacemouse_test.py --evdev /dev/input/event12
```

Ohne Button-Test:

```bash
python spacemouse_test.py --skip-buttons
```

Wenn du in `startx`/X11 bist, greift der Button-Test das `evdev`-Gerät standardmäßig exklusiv.
Dadurch sollten SpaceMouse-Tasten nicht mehr im Terminal oder Desktop Aktionen auslösen.

Nur falls das Probleme macht:

```bash
python spacemouse_test.py --no-grab
```

Ohne ANSI-Farben:

```bash
python spacemouse_test.py --no-color
```

## Bedienung

Das Script führt Schritt für Schritt durch den Test.

- **Rot** = fehlt / noch nicht getestet
- **Grün** = erkannt / bestanden
- **Gelb** = Hinweis / prüfen

Beim Tastentest wird zusätzlich geprüft:

- ob vor Testbeginn schon eine Taste aktiv ist
- ob nach dem Loslassen noch eine Taste gedrückt hängt
- ob das `evdev`-Gerät exklusiv gegriffen werden konnte

Besonders wichtig beim Z-Test:

```text
Z- : Kappe DRÜCKEN
Z+ : Kappe HOCHZIEHEN
```

Der Bewegungstest kann automatisch beendet werden, sobald alle 12 Richtungen ihr Max-Ziel erreicht haben.
Standardmäßig zählt eine Richtung erst nach 3 Messwerten über dem Bewegungsschwellwert, das Max-Ziel liegt bei 0.90 und der Bewegungstest läuft mindestens 20 Sekunden.

Im Live-Test bedeutet:

- `FEHLT` = Richtung noch nicht stabil erkannt
- `SEEN` = Richtung erkannt, aber Max-Ziel noch nicht erreicht
- `MAX` = Zielwert erreicht
- `peak- / +=0.96/1.00` = bisheriger Maximalwert negativ / positiv

Wenn der Test zu schnell durchläuft:

```bash
python spacemouse_test.py --range-seconds 90 --range-min-seconds 45 --direction-samples 5 --peak-target 0.95
```

Wenn du bewusst nur stärkere Ausschläge zählen willst:

```bash
python spacemouse_test.py --peak-target 0.95
```

## Ergebnis

Das Script erstellt:

```text
reports/spacemouse-test-YYYYMMDD-HHMMSS.txt
reports/spacemouse-test-YYYYMMDD-HHMMSS.json
```

Beispiel:

```text
Neutralstellung / Drift: PASS
6 Achsen / 12 Richtungen: PASS
Tasten Press + Release: PASS
GESAMTERGEBNIS: PASS
```

## Troubleshooting

Wenn `pyspacemouse` keine Geräte findet, zuerst prüfen:

```bash
pyspacemouse --list-hid
pyspacemouse --list-connected
pyspacemouse --test
```

Unter Linux sind häufig HID-/evdev-Berechtigungen das Problem. Für 3Dconnexion-Geräte kann eine udev-Regel für Vendor-ID `256f` helfen:

```bash
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="256f", MODE="0660", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/50-spacemouse.rules
echo 'SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTRS{idVendor}=="256f", MODE="0660", TAG+="uaccess"' | sudo tee -a /etc/udev/rules.d/50-spacemouse.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Danach SpaceMouse abziehen, wieder anstecken und das Terminal neu öffnen.

Wenn nur der Button-Test nicht verfügbar ist:

```bash
python spacemouse_test.py --list-devices
```

Suche in der `evdev`-Liste nach dem SpaceMouse-/3Dconnexion-Gerät. Wenn es nicht automatisch erkannt wird, den passenden Pfad manuell angeben:

```bash
python spacemouse_test.py --evdev /dev/input/event12
```

Wenn kein passendes `evdev`-Gerät auftaucht, ist die SpaceMouse wahrscheinlich noch nicht als Linux-Input-Gerät verfügbar oder die Berechtigungen fehlen. Mit USB/IP muss das Gerät auf dem Testrechner wirklich per `usbip attach` eingebunden sein, nicht nur auf dem entfernten Rechner sichtbar.

## Hinweis

Dies ist ein unabhängiger Funktionstest und kein offizielles 3Dconnexion-Diagnose- oder Kalibrierprotokoll.
