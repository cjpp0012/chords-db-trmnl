#!/usr/bin/env python3
"""
TRMNL Guitar Chord Webhook Server
Uses GitHub project: https://github.com/tombatossals/chords-db
Pushes {"merge_variables": ...} to TRMNL's Custom Plugin Webhook URL.
"""

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# --- Configuration via Environment Variables ---
TRMNL_WEBHOOK_URL = os.environ.get(
    "TRMNL_WEBHOOK_URL",
    "https://trmnl.com/api/custom_plugins/ea5b672f-aaf1-43a3-b9bc-53e695e165db"
)
# Default: Push a new chord every 30 minutes (1800 seconds).
# Note: TRMNL standard rate limit is 12 pushes/hour (min 300s interval).
PUSH_INTERVAL_SECONDS = int(os.environ.get("PUSH_INTERVAL_SECONDS", "1800"))
PORT = int(os.environ.get("PORT", "8085"))
CACHE_FILE = Path(os.environ.get("CACHE_FILE", "./guitar.json"))

GITHUB_RAW_URL = "https://raw.githubusercontent.com/tombatossals/chords-db/master/lib/guitar.json"
NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# --- Music Theory, Intervals & Style Knowledge Base ---
THEORY_CATALOG = {
    "major": {
        "title": "Major Triad",
        "family": "Major",
        "intervals": ["1", "3", "5"],
        "styles": ["Pop", "Rock", "Folk", "Country", "Classical"],
        "progressions": "I - IV - V - I  |  I - V - vi - IV",
        "theory": "Built from root, major 3rd (4 semitones), and perfect 5th (7 semitones). Establishes a bright, consonant, stable tonic resolution."
    },
    "minor": {
        "title": "Minor Triad",
        "family": "Minor",
        "intervals": ["1", "b3", "5"],
        "styles": ["Blues", "Rock", "Ballads", "Classical", "Metal"],
        "progressions": "i - bVI - bVII  |  ii - V - i",
        "theory": "Flattens the 3rd by a half step (3 semitones from root), creating a melancholic, introspective, or dramatic harmonic color."
    },
    "7": {
        "title": "Dominant 7th",
        "family": "Dominant",
        "intervals": ["1", "3", "5", "b7"],
        "styles": ["Blues", "Jazz", "Funk", "R&B", "Rockabilly"],
        "progressions": "V7 - I  |  I7 - IV7 - V7 (12-Bar Blues)",
        "theory": "Contains a restless tritone between the 3rd and b7th that drives tension back to the tonic (I) or acts as a gritty blues foundation."
    },
    "maj7": {
        "title": "Major 7th",
        "family": "Major",
        "intervals": ["1", "3", "5", "7"],
        "styles": ["Jazz", "Bossa Nova", "Neo-Soul", "Lo-Fi", "City Pop"],
        "progressions": "ii7 - V7 - Imaj7  |  IVmaj7 - Imaj7",
        "theory": "Adds a natural 7th (11 semitones) to a major triad. Produces lush, dreamy, nostalgic warmth prized in jazz and Neo-Soul voicings."
    },
    "m7": {
        "title": "Minor 7th",
        "family": "Minor",
        "intervals": ["1", "b3", "5", "b7"],
        "styles": ["Jazz", "Funk", "Neo-Soul", "R&B", "Fusion"],
        "progressions": "ii7 - V7 - Imaj7  |  i7 - IV7 (Dorian Vamp)",
        "theory": "Softens the minor triad with a flattened 7th. Serves as the foundational ii7 chord in jazz or a smooth Dorian groove chord."
    },
    "m7b5": {
        "title": "Half-Diminished 7th",
        "family": "Diminished",
        "intervals": ["1", "b3", "b5", "b7"],
        "styles": ["Jazz Standards", "Bossa Nova", "Film Score", "Neo-Soul"],
        "progressions": "iiø7 - V7b9 - i (Minor ii-V-i)",
        "theory": "Combines a diminished triad with a minor 7th. Functions primarily as the pre-dominant ii chord in minor-key turnarounds."
    },
    "dim7": {
        "title": "Full Diminished 7th",
        "family": "Diminished",
        "intervals": ["1", "b3", "b5", "bb7"],
        "styles": ["Jazz", "Classical", "Gypsy Jazz", "Gospel Passing"],
        "progressions": "I - #idim7 - ii7 - V7",
        "theory": "Symmetrical stack of minor 3rds (3 semitones apart). Any chord tone can act as root, making it a powerhouse for chromatic modulation."
    },
    "sus4": {
        "title": "Suspended 4th",
        "family": "Suspended",
        "intervals": ["1", "4", "5"],
        "styles": ["Classic Rock", "Acoustic Folk", "Modal Jazz"],
        "progressions": "Dsus4 - D - Dsus2 - D  |  V7sus4 - V7 - I",
        "theory": "Replaces the 3rd with a perfect 4th, suspending major/minor identity and creating open tension that wants to resolve down to the 3rd."
    },
    "sus2": {
        "title": "Suspended 2nd",
        "family": "Suspended",
        "intervals": ["1", "2", "5"],
        "styles": ["Indie Rock", "Post-Rock", "Midwest Emo", "Pop"],
        "progressions": "Isus2 - IVsus2 - V",
        "theory": "Replaces the 3rd with a major 2nd. Offers an airy, modern, ringing resonance without the pull of a traditional triad."
    },
    "9": {
        "title": "Dominant 9th",
        "family": "Extended Dominant",
        "intervals": ["1", "3", "5", "b7", "9"],
        "styles": ["Funk", "Soul", "Blues", "Jazz-Funk"],
        "progressions": "I9 Funk Vamp  |  ii7 - V9 - Imaj7",
        "theory": "Extends the dominant 7th with a major 9th. A signature rhythm guitar chord in funk and soul for percussive upper-structure voicings."
    },
    "m9": {
        "title": "Minor 9th",
        "family": "Extended Minor",
        "intervals": ["1", "b3", "5", "b7", "9"],
        "styles": ["Neo-Soul", "Smooth Jazz", "R&B", "Lo-Fi Hip Hop"],
        "progressions": "im9 - IV13  |  iim9 - V13 - Imaj9",
        "theory": "Stacks a luminous major 9th over a minor 7th shell, delivering velvety sophistication and rich harmonic depth."
    },
    "maj9": {
        "title": "Major 9th",
        "family": "Extended Major",
        "intervals": ["1", "3", "5", "7", "9"],
        "styles": ["Jazz Ballads", "Bossa Nova", "Math Rock", "City Pop"],
        "progressions": "Imaj9 - vi9 - iim9 - V13",
        "theory": "Adds both the natural 7th and 9th above a major triad for an expansive, shimmering tonic chord."
    },
    "aug": {
        "title": "Augmented Triad",
        "family": "Augmented",
        "intervals": ["1", "3", "#5"],
        "styles": ["Jazz Turnarounds", "Psychedelic Rock", "Film Scores"],
        "progressions": "I - I+ - I6 - I7  |  V+ - I",
        "theory": "Symmetrical triad of two stacked major 3rds. The raised 5th creates an unsettled, dreamlike upward pull toward the 6th or tonic."
    }
}

CHORDS_DB = None
LAST_PAYLOAD = {}


def load_github_chords_db():
    """Downloads tombatossals/chords-db guitar.json once and caches it locally."""
    global CHORDS_DB
    if CHORDS_DB is not None:
        return CHORDS_DB

    if CACHE_FILE.exists():
        print(f"[DB] Loading cached chords-db from {CACHE_FILE}")
        CHORDS_DB = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return CHORDS_DB

    print(f"[DB] Fetching tombatossals/chords-db from {GITHUB_RAW_URL} ...")
    req = urllib.request.Request(
        GITHUB_RAW_URL,
        headers={"User-Agent": "TRMNL-Guitar-Chord-Webhook/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw_data = resp.read().decode("utf-8")
        CACHE_FILE.write_text(raw_data, encoding="utf-8")
        CHORDS_DB = json.loads(raw_data)
    return CHORDS_DB


def generate_compact_svg(position):
    """
    Generates a minified, 1-bit e-ink optimized SVG fretboard card (<1KB)
    so the total webhook payload stays well under TRMNL's 5KB limit.
    """
    frets = position["frets"]
    fingers = position["fingers"]
    barres = position.get("barres", [])
    base_fret = position.get("baseFret", 1)

    w, h = 230, 250
    left, top = 40, 32
    gw, gh = 160, 192
    dx = gw / 5.0
    dy = gh / 4.0

    parts = [f'<svg viewBox="0 0 {w} {h}" width="220" height="240" xmlns="http://www.w3.org/2000/svg">']

    # Nut
    nut_w = 7 if base_fret == 1 else 2
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left+gw}" y2="{top}" stroke="#000" stroke-width="{nut_w}"/>')

    if base_fret > 1:
        parts.append(f'<text x="{left-10}" y="{top+dy/2+5}" font-family="monospace" font-size="15" font-weight="bold" text-anchor="end">{base_fret}fr</text>')

    # Frets
    for i in range(1, 5):
        y = int(top + i * dy)
        parts.append(f'<line x1="{left}" y1="{y}" x2="{left+gw}" y2="{y}" stroke="#000" stroke-width="2"/>')

    # Strings
    for s in range(6):
        x = int(left + s * dx)
        sw = 2.5 if s < 2 else 1.8
        parts.append(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{top+gh}" stroke="#000" stroke-width="{sw}"/>')

    # Barres
    for bf in barres:
        bs = [i for i, f in enumerate(frets) if f >= bf]
        if len(bs) >= 2:
            x1 = int(left + min(bs) * dx)
            x2 = int(left + max(bs) * dx)
            y = int(top + (bf - 0.5) * dy)
            parts.append(f'<rect x="{x1-10}" y="{y-10}" width="{x2-x1+20}" height="20" rx="10" fill="#000"/>')

    # Fingers & Open/Muted strings
    for s, f in enumerate(frets):
        x = int(left + s * dx)
        fn = fingers[s] if s < len(fingers) else 0
        if f == -1:
            parts.append(f'<text x="{x}" y="{top-10}" font-family="sans-serif" font-size="18" font-weight="900" text-anchor="middle">×</text>')
        elif f == 0:
            parts.append(f'<circle cx="{x}" cy="{top-16}" r="6" stroke="#000" stroke-width="2.5" fill="#fff"/>')
        else:
            y = int(top + (f - 0.5) * dy)
            parts.append(f'<circle cx="{x}" cy="{y}" r="11" fill="#000"/>')
            if fn > 0:
                parts.append(f'<text x="{x}" y="{y+5}" font-family="sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#fff">{fn}</text>')

    parts.append("</svg>")
    return "".join(parts)


def build_webhook_payload():
    """Selects a random chord + voicing and packages TRMNL merge_variables."""
    db = load_github_chords_db()
    chords_dict = db["chords"]

    key_choice = random.choice(list(chords_dict.keys()))
    chord_list = chords_dict[key_choice]

    preferred = [c for c in chord_list if c["suffix"] in THEORY_CATALOG]
    chord = random.choice(preferred if preferred and random.random() < 0.85 else chord_list)

    positions = chord["positions"]
    idx = random.randrange(len(positions))
    pos = positions[idx]

    key_display = chord["key"]
    suffix = chord["suffix"]
    meta = THEORY_CATALOG.get(suffix, {
        "title": f"{suffix.upper()} Chord",
        "family": "Extended / Altered",
        "intervals": ["1", "3", "5", suffix],
        "styles": ["Jazz", "Fusion", "Contemporary", "Session"],
        "progressions": "ii - V - I  |  Chromatic Voice Leading",
        "theory": f"Specialized {suffix} voicing from tombatossals/chords-db adding upper-structure color or altered harmonic tension."
    })

    midi_vals = pos.get("midi", [])
    pitch_classes = []
    for m in midi_vals:
        n = NOTE_NAMES[m % 12]
        if n not in pitch_classes:
            pitch_classes.append(n)

    used_fingers = sorted({f for f in pos.get("fingers", []) if f > 0})
    fingers_label = ", ".join(str(f) for f in used_fingers) if used_fingers else "Open"

    standard_midi = [40, 45, 50, 55, 59, 64]
    base_fret = pos.get("baseFret", 1)
    string_notes = []
    for s_idx, f_val in enumerate(pos["frets"]):
        if f_val == -1:
            string_notes.append("X")
        elif f_val == 0:
            string_notes.append(NOTE_NAMES[standard_midi[s_idx] % 12])
        else:
            actual = (base_fret + f_val - 1) if base_fret > 1 else f_val
            string_notes.append(NOTE_NAMES[(standard_midi[s_idx] + actual) % 12])

    chord_label = f"{key_display}{'' if suffix == 'major' else ('m' if suffix == 'minor' else suffix)}"

    merge_variables = {
        "chord_name": chord_label,
        "full_title": f"{key_display} {meta['title']}",
        "family": meta["family"],
        "voicing_index": idx + 1,
        "total_voicings": len(positions),
        "base_fret": base_fret,
        "svg_diagram": generate_compact_svg(pos),
        "string_notes": string_notes,
        "fingers_label": fingers_label,
        "intervals": meta["intervals"],
        "midi_notes": pitch_classes,
        "midi_list": ", ".join(str(m) for m in midi_vals),
        "theory_summary": meta["theory"],
        "progressions": meta["progressions"],
        "styles": meta["styles"]
    }

    return {"merge_variables": merge_variables}


def push_to_trmnl():
    """POSTs the generated merge_variables payload to TRMNL's Webhook URL."""
    global LAST_PAYLOAD
    payload = build_webhook_payload()
    LAST_PAYLOAD = payload
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    chord_name = payload["merge_variables"]["chord_name"]

    print(f"[WEBHOOK] Pushing '{chord_name}' ({len(body)} bytes) -> {TRMNL_WEBHOOK_URL}")

    if "YOUR_PLUGIN_UUID_HERE" in TRMNL_WEBHOOK_URL:
        print("[WARN] TRMNL_WEBHOOK_URL is not configured yet! Skipping HTTP POST.")
        return False, "Missing TRMNL_WEBHOOK_URL", payload

    req = urllib.request.Request(
        TRMNL_WEBHOOK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "TRMNL-Guitar-Chord-Webhook/1.0"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            resp_text = resp.read().decode("utf-8")
            print(f"[WEBHOOK] Success ({status}): {resp_text}")
            return True, resp_text, payload
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"[WEBHOOK] HTTP Error {e.code}: {err_body}")
        return False, f"HTTP {e.code}: {err_body}", payload
    except Exception as e:
        print(f"[WEBHOOK] Error: {e}")
        return False, str(e), payload


def scheduler_loop():
    """Background thread that pushes a new chord on a fixed interval."""
    while True:
        try:
            push_to_trmnl()
        except Exception as exc:
            print(f"[SCHEDULER] Unexpected error: {exc}")
        time.sleep(PUSH_INTERVAL_SECONDS)


class WebhookControlHandler(BaseHTTPRequestHandler):
    """
    Local endpoints:
      GET  /preview -> Inspect the latest generated merge_variables JSON
      POST /trigger -> Immediately push a new random chord to TRMNL Webhook
    """
    def do_GET(self):
        if self.path == "/preview":
            data = LAST_PAYLOAD or build_webhook_payload()
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            msg = b"TRMNL Guitar Webhook Server Running. Use GET /preview or POST /trigger."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(msg)

    def do_POST(self):
        if self.path == "/trigger":
            ok, msg, payload = push_to_trmnl()
            resp = {
                "pushed": ok,
                "chord": payload["merge_variables"]["chord_name"],
                "payload_bytes": len(json.dumps(payload, separators=(",", ":"))),
                "trmnl_response": msg
            }
            body = json.dumps(resp, indent=2).encode("utf-8")
            self.send_response(200 if ok else 502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    load_github_chords_db()
    # Start background webhook pusher thread
    t = threading.Thread(target=scheduler_loop, daemon=True)
    t.start()

    print(f"[SERVER] Listening on http://0.0.0.0:{PORT} (POST /trigger to force push)")
    HTTPServer(("0.0.0.0", PORT), WebhookControlHandler).serve_forever()
