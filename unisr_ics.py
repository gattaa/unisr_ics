#!/usr/bin/env python3
"""UniSR EasyCourse weekly grid -> .ics (stdlib only).

Usage: python3 unisr_ics.py out.ics [weeks]   e.g. weeks = 1-20 (default)
"""
import hashlib, re, sys, urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

BASE = ("https://easycourse.unisr.it/easycourse-new/pubblicazioni-riservate/standardGrid/"
        "figlia-4/2026-2027/s1/riservato?catena=S1&ricercaIndex=Corso+di+studi"
        "&CorsoDiStudio=459&annoCorso=1086&curriculum=1739&settimana={}")  # linea rossa, 2° anno


class Grid(HTMLParser):
    """Walks the direct children of div.orario-grid: 7 per row (ora + Mon..Sat).
    Header row holds dates; each lesson repeats once per 30-min slot it covers."""

    def __init__(self):
        super().__init__()
        self.depth = 0          # depth inside .orario-grid (0 = outside)
        self.col = -1           # index of current direct child
        self.dates = {}         # column -> "dd-mm-yyyy"
        self.text = ""
        self.lessons = {}       # dedupe key -> lesson dict

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.depth == 0:
            if tag == "div" and a.get("class") == "orario-grid":
                self.depth = 1
            return
        if tag in ("br", "img", "input", "hr", "meta", "link"):
            return
        self.depth += 1
        if self.depth == 2:
            self.col += 1
            self.text = ""
        if "lezione" == a.get("class") and "data-ora-inizio" in a:
            d = self.dates.get(self.col % 7)
            if d:
                self.lessons[(d, a["data-id"], a["data-ora-inizio"], a.get("data-aula"))] = {"date": d, **a}

    def handle_endtag(self, tag):
        if self.depth == 0 or tag in ("br", "img", "input", "hr", "meta", "link"):
            return
        if self.depth == 2 and 1 <= self.col <= 6:
            m = re.search(r"\d{2}-\d{2}-\d{4}", self.text)
            if m:
                self.dates[self.col] = m.group()
        self.depth -= 1

    def handle_data(self, data):
        if self.depth >= 2 and self.col <= 6:
            self.text += data


def parse(html):
    i = html.find('class="orario-grid"')
    if i < 0:
        return []
    g = Grid()
    g.feed(html[html.rfind("<", 0, i):])  # skip the 30 MB of dropdown JSON before the grid
    return list(g.lessons.values())


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    b = line.encode()
    out = []
    while len(b) > 74:
        cut = 74
        while (b[cut] & 0xC0) == 0x80:  # don't split a UTF-8 char
            cut -= 1
        out.append(b[:cut].decode())
        b = b[cut:]
    out.append(b.decode())
    return "\r\n ".join(out)


def to_ics(lessons):
    import json
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//unisr-ics//IT", "CALSCALE:GREGORIAN",
         "X-WR-CALNAME:UniSR Linea Rossa", "X-WR-TIMEZONE:Europe/Rome",
         # ponytail: minimal Europe/Rome VTIMEZONE, fine for CET/CEST since 1996 rules
         "BEGIN:VTIMEZONE", "TZID:Europe/Rome",
         "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
         "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
         "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
         "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
         "END:VTIMEZONE"]
    for x in sorted(lessons, key=lambda x: (x["date"][6:] + x["date"][3:5] + x["date"][:2], x["data-ora-inizio"])):
        dd, mm, yy = x["date"].split("-")
        day = yy + mm + dd
        try:
            prof = ", ".join(f'{p["Nome"].title()} {p["Cognome"].title()}' for p in json.loads(x.get("data-docenti") or "[]"))
        except ValueError:
            prof = ""
        loc = " - ".join(filter(None, [x.get("data-aula"), x.get("data-sede")]))
        uid = hashlib.sha1(f'{day}{x["data-id"]}{x["data-ora-inizio"]}{x.get("data-aula")}'.encode()).hexdigest()
        L += ["BEGIN:VEVENT", f"UID:{uid}@unisr-ics", f"DTSTAMP:{stamp}",
              f"DTSTART;TZID=Europe/Rome:{day}T{x['data-ora-inizio'].replace(':', '')}00",
              f"DTEND;TZID=Europe/Rome:{day}T{x['data-ora-fine'].replace(':', '')}00",
              f"SUMMARY:{esc(x.get('data-titolo', '').strip())}",
              f"LOCATION:{esc(loc)}", f"DESCRIPTION:{esc(prof)}", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in L) + "\r\n"


def fetch(week):
    req = urllib.request.Request(BASE.format(week), headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read().decode("utf-8", "replace")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "unisr.ics"
    a, b = map(int, (sys.argv[2] if len(sys.argv) > 2 else "1-20").split("-"))
    from concurrent.futures import ThreadPoolExecutor

    def week(w):
        try:
            got = parse(fetch(w))
        except Exception as e:  # one slow/broken week shouldn't kill the whole calendar
            print(f"week {w}: {e}", file=sys.stderr)
            return []
        print(f"week {w}: {len(got)} lessons", file=sys.stderr)
        return got

    # each week is a ~36 MB page that takes ~3 min; 4 at a time keeps it polite
    with ThreadPoolExecutor(4) as ex:
        lessons = [x for got in ex.map(week, range(a, b + 1)) for x in got]
    if not lessons:
        sys.exit("no lessons parsed, not overwriting calendar")
    open(out, "w", encoding="utf-8").write(to_ics(lessons))
