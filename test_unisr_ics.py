from unisr_ics import parse, to_ics

L = '<div class="lezione" data-id="{id}" data-titolo="{t}" data-ora-inizio="{s}" data-ora-fine="{e}" data-aula="A1" data-sede="VASARI" data-docenti=\'[{{"Nome":"LUCA","Cognome":"ROSSI"}}]\'></div>'
cells = lambda *xs: "".join(f'<div class="grid-cell">{x}</div>' for x in xs)
HTML = ('<script>window.datiSelect={"junk":"orario"}</script><div class="orario-grid">'
        '<div class="grid-header">Ora</div>'
        + "".join(f'<div class="grid-header">Giorno <br> {d:02d}-10-2026</div>' for d in range(5, 11))
        + '<div class="grid-ora">08:30</div>'
        + cells(L.format(id=1, t="Fisio, 1", s="08:30", e="10:30"), "", "", "", "", L.format(id=2, t="Isto", s="08:30", e="09:30"))
        + '<div class="grid-ora">09:00</div>'
        + cells(L.format(id=1, t="Fisio, 1", s="08:30", e="10:30"), "", "", "", "", "")  # same lesson, next slot
        + '</div>')

got = sorted((x["date"], x["data-titolo"]) for x in parse(HTML))
assert got == [("05-10-2026", "Fisio, 1"), ("10-10-2026", "Isto")], got
ics = to_ics(parse(HTML))
assert "DTSTART;TZID=Europe/Rome:20261005T083000" in ics and "SUMMARY:Fisio\\, 1" in ics and "Luca Rossi" in ics
print("ok")
