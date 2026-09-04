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
- TXT-Report für Verkauf / Willhaben
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
  --button-seconds 90
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

Besonders wichtig beim Z-Test:

```text
Z- : Kappe DRÜCKEN
Z+ : Kappe HOCHZIEHEN
```

Der Bewegungstest kann automatisch beendet werden, sobald alle 12 Richtungen erkannt wurden.

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

## Hinweis

Dies ist ein unabhängiger Funktionstest und kein offizielles 3Dconnexion-Diagnose- oder Kalibrierprotokoll.
