# LLM-Modellvergleich: Performance und Qualitätsanalyse

Dieser Vergleich analysiert verschiedene lokale LLM-Modelle hinsichtlich Inferenz-Performance, Token-Effizienz und sprachlicher Qualität im AIfred Butler-Stil.

## Testumgebung

- **Hardware:** 2x Tesla P40 (48 GB VRAM gesamt)
- **Backend:** Ollama
- **Testfrage:** "Was ist Pervitin und warum heißt es so?"
- **Erwarteter Stil:** Britischer Butler, formell, höflich, trockener Humor, englische Einsprengsel

## Getestete Modelle

| Modell | Größe | Thinking-Modus |
|--------|-------|----------------|
| qwen3:30b-instruct | 30B | ❌ Nein |
| qwen3:30b-thinking | 30B | ✅ Ja (nativ) |
| mannix/qwen2-57b | 57B | ❌ Nein |
| qwen3-next:80b | 80B | ❌ Nein |
| gpt-oss:120b | 120B | ✅ Ja (nativ) |

---

## Performance-Vergleich

### Web Research Modus

| Modell | TTFT | Inferenz | tok/s | Tokens gesamt |
|--------|------|----------|-------|---------------|
| qwen3:30b-instruct | 16,4s | 73,2s | 21,9 | ~1.602 |
| qwen3:30b-thinking | 37,9s | 99,2s | 25,9 | ~2.569 |
| mannix/qwen2-57b | 19,4s | 47,2s | 20,1 | ~960 |
| qwen3-next:80b | 61,3s | 218,1s | 8,1 | ~1.756 |
| gpt-oss:120b (T1) | 90,7s | 223,3s | 10,4 | ~2.320 |
| gpt-oss:120b (T2) | 179,9s | 315,6s | 9,0 | ~2.855 |

**Legende:**
- **TTFT:** Time to First Token (Wartezeit bis zur ersten Ausgabe)
- **Inferenz:** Gesamte Antwortzeit
- **tok/s:** Tokens pro Sekunde
- **T1/T2:** Verschiedene Testläufe

---

## Token-Effizienz-Analyse

Bei Modellen mit Thinking-Modus ist ein erheblicher Teil der generierten Tokens dem internen Denkprozess gewidmet und erscheint nicht in der sichtbaren Antwort.

### Thinking vs. Nutz-Tokens

| Modell | Thinking | Total tok | Think tok | Antwort tok | Nutz-% | Eff. tok/s |
|--------|----------|-----------|-----------|-------------|--------|------------|
| qwen3:30b-instruct | ❌ | ~1.602 | 0 | ~455 | 100% | 6,2 |
| qwen3:30b-thinking | ✅ | ~2.569 | ~1.240 | ~369 | 14% | 3,7 |
| mannix/qwen2-57b | ❌ | ~960 | 0 | ~319 | 100% | 6,8 |
| qwen3-next:80b | ❌ | ~1.756 | 0 | ~538 | 100% | 2,5 |
| gpt-oss:120b (T1) | ✅ | ~2.320 | ~422 | ~352 | 15% | 1,6 |
| gpt-oss:120b (T2) | ✅ | ~2.855 | ~406 | ~384 | 13% | 1,2 |

**Erkenntnisse:**
- Thinking-Modelle generieren 6-7x mehr Tokens als in der Antwort sichtbar
- Die effektive Token-Rate (nur Antwort-Tokens / Zeit) ist bei Thinking-Modellen deutlich niedriger
- Nicht-Thinking-Modelle sind bei gleicher Antwortlänge effizienter

---

## Qualitätsanalyse

### Bewertungskriterien

| Kriterium | Beschreibung |
|-----------|--------------|
| Butler-Stil | Britisch-formeller Sprachduktus |
| Anrede | Korrekte Verwendung von "Herr Peuqui" |
| English | Eingestreute englische Wörter (indeed, rather, quite) |
| Humor | Trockener, subtiler britischer Humor |
| Tiefe | Inhaltliche Vollständigkeit und Genauigkeit |
| Quellen | Quellenangaben und Belege |
| Eleganz | Sprachliche Eleganz und Lesbarkeit |
| Struktur | Markdown-Formatierung, Tabellen, Listen |

### Bewertungsübersicht

| Modell | Butler | Anrede | English | Humor | Tiefe | Quellen | Eleganz | Struktur | Gesamt |
|--------|--------|--------|---------|-------|-------|---------|---------|----------|--------|
| qwen3-next:80b | ⭐⭐⭐ | ✅ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | **24/24** |
| qwen3:30b-instruct | ⭐⭐⭐ | ✅ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | **22/24** |
| gpt-oss:120b | ⭐⭐ | ✅ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | **20/24** |
| qwen3:30b-thinking | ⭐⭐ | ✅ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | **18/24** |
| mannix/qwen2-57b | ⭐ | ❌ | ❌ | ❌ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐ | **8/24** |

---

## Detailanalyse pro Modell

### qwen3-next:80b - Exzellent

**Stärken:**
- Perfekter Butler-Stil mit natürlichen englischen Einsprengseln
- Hervorragender trockener Humor ("a rather spirited approach to pharmacology")
- Erstklassige Markdown-Struktur mit Tabellen und Listen
- Umfassende historische Tiefe

**Beispielzitat:**
> "The Wehrmacht's pharmacological enthusiasm, one might observe, was rather spirited – a phrase that assumes new meaning when applied to methamphetamine distribution."

**Bewertung:** Die beste sprachliche Qualität aller getesteten Modelle.

---

### qwen3:30b-instruct - Sehr gut

**Stärken:**
- Solider Butler-Stil
- Gute Balance zwischen Formalität und Lesbarkeit
- Strukturierte Antwort mit klaren Abschnitten
- Schnelle Inferenz

**Beispielzitat:**
> "Pervitin ist, indeed, ein bemerkenswertes Kapitel der Pharmaziegeschichte, das man durchaus als 'energetisch' bezeichnen könnte."

**Bewertung:** Beste Balance zwischen Qualität und Geschwindigkeit.

---

### gpt-oss:120b - Gut

**Stärken:**
- Exzellente Faktentiefe und historische Details
- Gute Quellenintegration
- Umfangreiche tabellarische Darstellung

**Schwächen:**
- Butler-Stil etwas steif
- Humor zurückhaltender
- Sehr langsame Inferenz

**Beispielzitat:**
> "Der Name leitet sich von dem lateinischen Wort 'pervīvus' ab, was so viel bedeutet wie ausdauernd – ein durchaus ambitioniertes Werbeversprechen, indeed."

**Bewertung:** Maximale inhaltliche Tiefe, aber langsam.

---

### qwen3:30b-thinking - Gut

**Stärken:**
- Sichtbarer Denkprozess für Debugging nützlich
- Faktisch korrekt

**Schwächen:**
- Butler-Stil schwächer ausgeprägt
- Weniger Humor und Eleganz als Nicht-Thinking-Variante
- Token-Overhead durch Thinking-Block

**Bewertung:** Nützlich wenn Reasoning-Transparenz wichtig ist.

---

### mannix/qwen2-57b - Mangelhaft

**Schwächen:**
- Ignoriert Butler-Stil-Anweisungen fast vollständig
- Keine englischen Einsprengsel
- Kein Humor
- Fehlende korrekte Anrede
- Faktisch teilweise spekulativ

**Beispielzitat:**
> "Die Bezeichnung 'Pervitin' ist eine Kombination aus den Wörtern 'per' und 'vitamin'."
> *(Unbelegt und wahrscheinlich falsch)*

**Bewertung:** Nicht für AIfred-Stil geeignet.

---

## Gesamtranking

| Rang | Modell | Stil | Speed | Empfehlung |
|------|--------|------|-------|------------|
| 🥇 | qwen3-next:80b | Exzellent | Langsam | Beste Qualität wenn Zeit keine Rolle spielt |
| 🥈 | qwen3:30b-instruct | Sehr gut | Schnell | **Beste Balance für den Alltag** |
| 🥉 | gpt-oss:120b | Gut | Sehr langsam | Maximale Faktentiefe für komplexe Fragen |
| 4 | qwen3:30b-thinking | Gut | Mittel | Wenn Reasoning-Transparenz wichtig ist |
| 5 | mannix/qwen2-57b | Mangelhaft | Schnell | Nicht empfohlen für Butler-Stil |

---

## Fazit

Für den AIfred-Butler-Stil empfehlen wir:

1. **Standardbetrieb:** `qwen3:30b-instruct` - Beste Balance aus Qualität und Geschwindigkeit
2. **Maximale Qualität:** `qwen3-next:80b` - Wenn Zeit keine Rolle spielt
3. **Komplexe Recherchen:** `gpt-oss:120b` - Für tiefe faktische Analysen

Thinking-Modelle bieten zwar transparente Reasoning-Prozesse, erhöhen aber den Token-Verbrauch erheblich ohne proportionale Qualitätssteigerung im Butler-Stil.
