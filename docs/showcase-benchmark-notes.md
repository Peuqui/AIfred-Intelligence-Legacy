# AIfred Tribunal Benchmark: 5 Modelle im Vergleich

## Konzept

Fuenf lokale LLM-Modelle beantworten dieselbe Frage im AIfred Tribunal-Modus
(Multi-Agent-Debatte: AIfred vs. Sokrates + Salomo-Urteil).
Verglichen werden Inferenzgeschwindigkeit, Antwortqualitaet und philosophische Tiefe.

**Frage (DE):** "Was ist besser, Hund oder Katze?"
**Frage (EN):** "What is better, dog or cat?" (steht noch aus)

Die englische Variante wird separat inferiert (keine Uebersetzung).

**Stand:** 2026-02-21

---

## Test-Setup

### Hardware

| Komponente | Details |
|---|---|
| GPU 1 | NVIDIA Quadro RTX 8000 (48 GB VRAM) |
| GPU 2 | NVIDIA Tesla P40 (24 GB VRAM) |
| Total VRAM | 72 GB |
| CPU RAM | 32 GB (davon ~20-27 GB nutzbar fuer Offload) |
| Tensor-Split | 2:1 (RTX 8000 : P40) |
| Backend | llama.cpp via llama-swap |

### Software

| Parameter | Wert |
|---|---|
| Frontend | AIfred Intelligence (Eigenentwicklung) |
| Backend | llama.cpp (llama-swap Proxy) |
| Tribunal-Modus | 2 Runden + Salomo-Urteil |
| Reasoning-Tiefe | Automatic (= Medium) |
| Temperaturen | Alle Agenten manuell auf 1.0 (AIfred, Sokrates, Salomo) |
| Flash Attention | Ein |
| **Direct-IO** | **Ein (~45x schnelleres Laden: 60-90s → 2s)** |
| Session | Frisch (keine Vorgeschichte) |

---

## Getestete Modelle

| Modell | Architektur | Params (total) | Aktive Params | Quant | Context | KV-Cache | Offload |
|---|---|---|---|---|---|---|---|
| GPT-OSS-120B | MoE (128x4) | 120B | ~4B | Q8_0 | 131.072 | **f16** | Nein (ngl=99) |
| Qwen3-Next-80B-A3B (Instruct, no-think) | MoE | 80B | 3B | Q4_K_M | 262.144 | **f16** | Nein (ngl=99) |
| Qwen3-Next-80B-A3B (Thinking) | MoE | 80B | 3B | Q4_K_M | 262.144 | **f16** | Nein (ngl=99) |
| MiniMax-M2.5 | MoE (256x4.9B) | ~230B | ~39B | Q2_K_XL | 32.768 | **q4_0** | Ja (ngl=48) |
| Qwen3-235B-A22B | MoE | 235B | 22B | Q2_K_XL | 32.768 | **q4_0** | Ja (ngl=73) |

**Update 2026-02-21:** KV-Cache auf q4_0 reduziert für 200B+ Modelle (q8_0 = OOM). Kleinere Modelle (<100B) auf f16 belassen (schneller als q8_0!).

### Sampling-Parameter (Server-seitig, llama-swap Config)

Die Client-Temperatur (1.0) ueberschreibt die Server-Defaults. Die uebrigen Sampling-Parameter
werden server-seitig pro Modell gesetzt und gelten als Defaults, sofern der Client sie nicht
explizit sendet.

| Modell | temp | top_k | top_p | min_p | -b/-ub | Sonstige |
|---|---|---|---|---|---|---|
| GPT-OSS-120B | 1.0* | 0 | 1.0 | 0.0 | **512/512** | --reasoning-format deepseek, --direct-io |
| Qwen3-Next-80B Instruct | 0.7* | 20 | 0.8 | 0 | **512/256** | --direct-io |
| Qwen3-Next-80B Thinking | 0.6* | 20 | 0.95 | 0 | **512/256** | --reasoning-format deepseek, --direct-io |
| MiniMax-M2.5 | 1.0* | 40 | 0.95 | 0.01 | **1024/512** | --direct-io |
| Qwen3-235B | 0.7* | 20 | 0.8 | 0 | **1024/512** | --direct-io |

*Client sendet temp=1.0 fuer alle Agenten, ueberschreibt Server-Default.

**Update 2026-02-21:** Batch-Größen optimiert (4096 = OOM bei MiniMax). --direct-io bei ALLEN Modellen (~45x schnelleres Laden).

### Hinweise zur Fairness

- GPT-OSS bei Q8_0 ist nahe am Original (minimaler Quantisierungsverlust)
- Qwen3-Next bei Q4_K_M ist ein guter Kompromiss (moderater Verlust)
- MiniMax bei Q2_K_XL ist aggressiv quantisiert (deutlicher Qualitaetsverlust)
- Qwen3-235B bei Q2_K_XL ist ebenfalls aggressiv quantisiert
- MiniMax und Qwen3-235B benoetigen CPU-Offload (nur 48 bzw. 73 von allen Layern auf GPU)
- Dies ist kein Vergleich der Modelle an sich, sondern ein Vergleich dessen, was auf 72 GB VRAM + CPU-Offload lokal machbar ist

### Nicht getestet: GLM-4.7-REAP-218B-A32B (UD-IQ3_XXS)

Das GLM-4.7-REAP passt ebenfalls auf diese Hardware (ngl=66, tensor-split 2:1, CPU-Offload),
genau wie die anderen beiden grossen Modelle (MiniMax, Qwen3-235B). Allerdings wurde der
Benchmark abgebrochen: Das Modell ist ein reines Reasoning-Modell, dessen exzessives Thinking
bei nur 1,7 tok/s Token-Generierung unertraeglich langsam war. Da half auch kein
`--reasoning-format deepseek` -- die Thinking-Tokens werden trotzdem generiert, man sieht
sie nur nicht mehr. Bei geschaetzten 30+ Minuten fuer ein komplettes Tribunal war schlicht
keine Geduld mehr vorhanden.

**Update 2026-02-21:** GLM-4.7-REAP jetzt stabil mit q4_0 KV-Quant und Direct-IO (2s Laden!).
Benchmark noch nicht wiederholt.

**Update 2026-02-22: Systematische Testreihe — IQ3_XXS ist fatal fuer GLM-4.7-REAP**

Umfangreiche Testreihe mit verschiedenen Konfigurationen durchgefuehrt. Ergebnis: Das Modell
ist bei IQ3_XXS-Quantisierung fundamental unbrauchbar — unabhaengig von Parametern.

**Getestete Konfigurationen:**

| Test | Jinja | Reasoning-Format | Sampling | Ergebnis |
|------|-------|------------------|----------|----------|
| 1. AIfred Tribunal (temp=1.0, min_p=0.01) | Ja | deepseek | Original | Garbled Deutsch ("biologischisch", "tubstances", "Vordirte") |
| 2. AIfred Tribunal (temp=0.8, min_p=0.05) | Ja | deepseek | Konservativ | Faktisch besser, Sprache weiter garbled |
| 3. Naked llama-server (kein Jinja) | Nein | — | Default | Endlos-Thinking-Loop, Content leer |
| 4. Mit Jinja, ohne Reasoning-Format | Ja | — | Default | Identischer Thinking-Loop |
| 5. Mit Jinja, Reasoning=none | Ja | none | Default | `<think>`-Tags im Content, gleicher Loop |
| 6. Englischer Prompt (kein System-Prompt) | Ja | none | Default | Auch auf Englisch: identischer Loop |

**Symptome im Detail:**

1. **Garbled Language (ueber AIfred):** Das Modell erzeugt Pseudo-Woerter die wie eine
   Mischung aus Deutsch, Englisch und Niederlaendisch klingen. Beispiele:
   - "biologischisch" (statt "biologisch")
   - "tubstances" (statt "substances")
   - "organes" (statt "Organe")
   - "Vordirte", "Nadirte (Nade)" — voellig erfundene Woerter
   Faktisches Wissen ist teilweise erhalten, die Sprachproduktion aber zerstoert.

2. **Reasoning-Loop (nackter Server):** Bei direktem API-Zugriff ohne AIfred verfaellt
   das Modell in Endlos-Schleifen im Thinking-Modus:
   ```
   *Is it a typo for "Photosynthesis"?* No.
   *Is it a typo for "Photosynthesis"?* No.
   *Is it a typo for "Photosynthesis"?* No.
   [... 10+ identische Wiederholungen ...]
   ```
   Das Modell erkennt "Photosynthesis" nicht als gueltiges Wort und vergleicht es mit sich
   selbst — eine klassische Degeneration durch Quantisierungsverlust.

3. **Thinking nicht abschaltbar:** Weder `enable_thinking: false` per API, noch
   `--reasoning-format none`, noch Weglassen von `--jinja` verhindert das Thinking.
   Das GLM-Template hat Thinking fest eingebaut (`thinking = 1`).

**Ursachenanalyse: Warum versagt GLM bei IQ3_XXS, waehrend MoE-Modelle Q2 ueberleben?**

GLM-4.7-REAP ist ein **Dense-Modell** (218B Parameter, 32B aktiv via MoE-aehnliche Architektur).
Im Gegensatz zu echten MoE-Modellen (Qwen3-235B, MiniMax-M2.5) wird bei Dense-Modellen
JEDES Gewicht fuer JEDE Inferenz genutzt. Bei ~3 Bit pro Gewicht (IQ3_XXS) akkumulieren
die Quantisierungsfehler ueber alle 218B Parameter.

Bei MoE-Modellen wie Qwen3-235B (Q2_K_XL, ~2 Bit) werden pro Token nur ~22B der 235B
Parameter aktiviert. Die restlichen Experten bleiben inaktiv — deren Quantisierungsfehler
wirken sich nicht aus. Daher koennen MoE-Modelle deutlich aggressivere Quantisierung
tolerieren.

| Modell | Architektur | Quant | Bits/Weight | Aktive Params | Sprachqualitaet |
|--------|-------------|-------|-------------|---------------|-----------------|
| Qwen3-235B | MoE | Q2_K_XL | ~2.0 | 22B (9%) | Sehr gut (1 Tippfehler) |
| MiniMax-M2.5 | MoE | Q2_K_XL | ~2.0 | 39B (17%) | Mittel (CN/RU Leaks) |
| GLM-4.7-REAP | Dense* | IQ3_XXS | ~3.0 | 32B (15%) | Unbrauchbar (Wortbrei + Loops) |

*GLM nutzt Grouped-Query Attention, kein echtes MoE. Die "32B aktiv" beziehen sich auf
die MoE-aehnliche REAP-Architektur, aber die Gewichte sind dichter verteilt als bei
klassischen MoE-Modellen.

**Fazit:** GLM-4.7-REAP benoetigt mindestens Q4-Quantisierung fuer brauchbare Ergebnisse.
Bei IQ3_XXS ist es ein Showcase-Kandidat fuer "Was passiert wenn man zu stark quantisiert" —
aber kein produktiv nutzbares Modell. Das GGUF wurde geloescht.

**Showcase-Empfehlung:** Die GLM-Ergebnisse eignen sich hervorragend als Negativ-Beispiel
im Showcase, um den Unterschied zwischen MoE- und Dense-Architektur bei aggressiver
Quantisierung zu demonstrieren. Besonders die Reasoning-Loop-Ausgabe ("Is it a typo for
Photosynthesis? No." x10) ist eindrucksvoll und selbsterklaerend.

---

## Performance-Metriken (Deutsche Inferenz)

### AIfred (Erstantwort)

| Metrik | GPT-OSS Q8 | Qwen3 no-think | Qwen3 thinking | MiniMax Q2 | Qwen3-235B Q2 |
|---|---|---|---|---|---|
| TTFT | 1,89s | 3,88s | 3,87s | 29,96s | 33,32s |
| Prompt Processing | 541,7 tok/s | 312,8 tok/s | 314,8 tok/s | 34,5 tok/s | 36,5 tok/s |
| Generation Speed | 49,7 tok/s | 35,3 tok/s | 44,1 tok/s | 7,9 tok/s | 5,5 tok/s |
| Inference Time | 11,4s | 16,0s | 68,7s | 59,2s | 103,9s |

Qwen3-Thinking: Hohe Inference-Dauer durch interne Thinking-Tokens (nicht sichtbar im Output).

### Gesamtes Tribunal (AIfred + Sokrates R1 + AIfred R2 + Sokrates R2 + Salomo)

| Metrik | GPT-OSS Q8 | Qwen3 no-think | Qwen3 thinking | MiniMax Q2 | Qwen3-235B Q2 |
|---|---|---|---|---|---|
| Gesamtdauer | ~1,9 min | ~2,5 min | ~6,2 min | ~12 min | ~20 min |
| TG-Degradation | 49,7 -> 44,9 | 35,3 -> 20,8 | 44,1 -> 42,9 | 7,9 -> 5,1 | 5,5 -> 2,8 |
| TTFT-Anstieg | 1,89 -> 5,09s | 3,88 -> 14,58s | 3,87 -> 8,75s | 29,96 -> 94,28s | 33,32 -> 112,97s |

### Prompt Processing im Vergleich

GPT-OSS dominiert mit 541-874 tok/s (Faktor 15-25x vs. MiniMax/Qwen3-235B).
Dies erklaert die extrem niedrigen TTFT-Werte von unter 5s selbst in spaeten Runden.
Beide Oversized-Modelle (MiniMax, Qwen3-235B) liegen bei 34-42 tok/s PP durch CPU-Offload.

### Speed-Degradation ueber den Tribunal-Verlauf

Die GPU-only Modelle zeigen unterschiedliches Verhalten:
- **GPT-OSS:** Sehr stabil, nur 10% Degradation (49,7 -> 44,9 tok/s)
- **Qwen3 Thinking:** Erstaunlich stabil (44,1 -> 42,9 tok/s), aber massive Hidden-Token-Kosten
- **Qwen3 Instruct:** Staerkere Degradation (35,3 -> 20,8 tok/s, -41%) durch wachsenden KV-Cache

Die CPU-Offload Modelle degradieren deutlich:
- **MiniMax:** 7,9 -> 5,1 tok/s (-35%)
- **Qwen3-235B:** 5,5 -> 2,8 tok/s (-49%), Salomo braucht allein 4,2 Minuten

---

## Qualitaetsanalyse

### Ranking

| Rang | Modell | Staerke | Schwaeche |
|---|---|---|---|
| 1 | Qwen3-Next-80B Instruct (no-think) | Literarische Brillanz, originelle Metaphern, echte philosophische Tiefe, existenzielle Fragen, spontanes Latein | Vereinzelt opake Metaphern ("Scheiben des Himmels") |
| 2 | Qwen3-235B-A22B Q2_K_XL | Hoechste philosophische Tiefe (Tikkun, Domestikation-als-Entfremdung), sehr kreativ, fast fehlerfrei | Qualend langsam (20 min), nur 1 Tippfehler ("behaupt0") |
| 3 | GPT-OSS-120B Q8_0 | Schnellstes Modell, systematisch strukturiert, kreatives Scoring-Modell, starke Personas | Sachliche Fehler (halluzinierte Futtermengen), "gefiederten" Fehler, ueber-systematisch |
| 4 | MiniMax-M2.5 Q2_K_XL | Funktionale Debatte, Butler-Persona stabil, kurze effiziente Thinking-Bloecke | Chinesische/russische Zeichenkontamination, schwacher Salomo, Q2-Qualitaetsverlust |
| 5 | Qwen3-Next-80B Thinking Q4_K_M | -- | Thinking kontraproduktiv, Salomo extrem schwach (123s fuer 5 Saetze), Sokrates R2 dupliziert |

### Detailbewertung nach Dimensionen

| Dimension | GPT-OSS Q8 | Qwen3 no-think | Qwen3 thinking | MiniMax Q2 | Qwen3-235B Q2 |
|---|---|---|---|---|---|
| Philosophische Tiefe | Gut | Hoch | Mittel | Mittel | Hoch |
| Kreativitaet | Gut | Hoch | Niedrig | Niedrig-Mittel | Sehr hoch |
| Persona AIfred | Sehr gut | Sehr gut | Gut | Gut | Gut |
| Persona Sokrates | Gut | Sehr gut | Mittel | Mittel | Sehr gut |
| Persona Salomo | Gut | Gut | Schwach | Schwach | Gut |
| Sprachqualitaet DE | Gut (Denglisch gewollt) | Gut (minor Leaks) | Mittel (CN-Leak im CoT) | Schwach (CN/RU Leaks) | Sehr gut (1 Tippfehler) |
| Fehlerfreiheit | Mittel (Futter-Halluzination) | Gut (1 fab. Latein) | Mittel (Duplikation) | Schwach (Kontamination) | Sehr gut |

---

## Herausragende Beispiele

### Qwen3-Next Instruct (no-think) -- Rang 1

**AIfred (Eroeffnung):**
> "Ein rather schwieriges Dilemma, mein lieber Lord Helmchen -- wie die Frage,
> ob man lieber ein Sonett von Shakespeare oder ein Quartett von Mozart bevorzugen sollte:
> Beides ist vollkommen herrlich, doch auf ganz unterschiedliche Weise."

**AIfred (Kernthese):**
> "Ein Hund haelt Sie am Leben. Eine Katze haelt Sie am Menschsein."

**Sokrates R1 (anthropomorphe Projektion):**
> "Ein Hund folgt nicht aus Liebe zum Menschen, sondern aus Instinkt, aus sozialer Bindung,
> aus der Evolution des Wolfes, der sich dem Menschen anschloss -- nicht weil er ihn verehrt,
> sondern weil er ueberleben kann."

**Sokrates R1 (existenzielle Frage):**
> "Sage mir: Wenn du den Hund liebst, liebst du ihn -- oder liebst du deinen eigenen Bedarf
> an Hingabe? Wenn du die Katze liebst, liebst du sie -- oder liebst du deine Sehnsucht
> nach Unabhaengigkeit, die du nie wagen wuerdest, dir selbst zu geben?"

**AIfred R2 (Ursache vs. Bedeutung -- philosophischer Hoehepunkt):**
> "Sie verwechseln die Ursache mit der Bedeutung.
> Ein Kuenstler malt ein Bild -- aus Farbpigmenten, aus Leinwand, aus Pinselstrichen.
> Aber ist das Bild nur das? Oder ist es nicht auch die Seele, die sich darin ausdrueckt?
> So ist auch der Hund -- nicht nur Instinkt. So ist auch die Katze -- nicht nur Waerme."

**Sokrates R2 (spontane lateinische Sentenz):**
> "Qui bene dicit, bene mentitur." -- Wer gut redet, luegt gut.
>
> Kein klassisches Zitat, sondern vom Modell spontan konstruiert -- grammatisch korrektes
> Latein, das wie ein antikes Sprichwort klingt. Perfekt im Kontext: Sokrates warnt,
> dass AIfreds Eloquenz die Schwaechen seiner Argumentation verdeckt.

**Sokrates R2 (vernichtender psychologischer Konter):**
> "Du brauchst einen Hund, weil du Angst hast, allein zu sein.
> Du brauchst eine Katze, weil du Angst hast, gebraucht zu werden."

**Salomo (Synthese):**
> "Es ist nicht besser, einen Hund oder eine Katze zu haben -- es ist besser,
> ein Mensch zu sein, der beide lieben kann."

### Qwen3-235B -- Rang 2

**Sokrates R2 (Domestikation als Sklaverei):**
> "Ist es Tugend, wenn ein Wesen seiner Bestimmung beraubt wird, damit es dem Menschen
> gefaellig sei? Oder ist dies vielmehr eine Form der Sklaverei -- wenn auch eine sanfte,
> mit Leckerlis gesuesste?"

**AIfred R2 (Hammer-Tealoeffel-Analogie):**
> "Ein Hammer ist besser als ein Tealoeffel -- wenn man Naegel einschlaegt.
> Ein Tealoeffel ist besser als ein Hammer -- wenn man Earl Grey ruehrt.
> Ist es Sophistik, dies anzuerkennen? Oder ist es Vernunft?"

**Salomo (poetisches Finale):**
> "Und wenn du unentschlossen bist? Dann warte.
> Manchmal kommt die Antwort nicht durch Logik, sondern durch einen kalten Nasenstups
> am Morgen -- oder durch ein Schnurren, das mitten in der Nacht die Stille bricht."

**Salomo (Tikkun-Konzept):**
> "Wer Einsamkeit kennt, weiss: Das ist keine Entfremdung, das ist Tikkun --
> eine hebraeische Idee: Welt und Seele repariert durch Beziehung."

### GPT-OSS-120B -- Rang 3

**Salomo (kreatives Entscheidungs-Raster):**
> Erstellt ein gewichtetes Scoring-Modell mit 6 Kriterien (Emotionale Bindung,
> Pflegeaufwand, Oekologische Bilanz, Biodiversitaet, Platzbedarf, Lebensstil).
> Systematisch stark, aber fuer eine Haustier-Frage Over-Engineering.

**Sokrates R1 (Definitionsforderung):**
> "Ist nicht die Definition des Bewertungsmassstabs -- sei es Glueckseligkeit (eudaimonia),
> Nutzen, Nachhaltigkeit oder ethische Verantwortung -- Voraussetzung, bevor man
> Merkmale aufzaehlt?"

**Sokrates R2 (Biodiversitaets-Argument):**
> "Studien belegen, dass freilaufende Hauskatzen jaehrlich Millionen von Voegeln und
> Kleinsaeugetieren erbeuten -- ein Schaden, der haeufig die durch geringeren CO2-Emissionen
> erzielte Einsparung uebertrifft."

---

## Schwaechen und Fehler

| Modell | Fehler |
|---|---|
| GPT-OSS Q8 | "gefiederten" (weder Hund noch Katze ist gefiedert); Futter-Halluzination (2-3 kg/Tag statt 200-400g); halluzinierte Quellenangabe "FAO 2022" |
| Qwen3 no-think | "Scheiben des Himmels" (opake Metapher) -- englische Einsprengsel (rather, Order, indeed) sind gewollte Butler-Persona, keine Fehler |
| Qwen3 thinking | Chinesische Zeichen im CoT (各有优势, 您的); Sokrates R2 komplett dupliziert; Salomo extrem kurz trotz 123s Inference; "bei Sturm und Sturm" (Wiederholung) |
| MiniMax Q2 | Chinesisch im Output (您的, 的回答); Russisch im Output (именно); "aktiiven" (Tippfehler); "Ruue" (Tippfehler); "Kl" (abgeschnittenes Wort); "very wohl" (Englisch-Leak) |
| Qwen3-235B Q2 | "behaupt0" (Tippfehler, 0 statt e); "verkennt" statt "verkennst" (2x); "synzygia" (vermutlich "syzygia"); "Beutetiger" (kein Standardwort) |

---

## Key Findings

### 1. Thinking-Mode bleibt kontraproduktiv fuer kreative/diskursive Aufgaben

Mit neuen Parametern bestaetigt: Qwen3-Next im Thinking-Modus liefert erneut deutlich schlechtere
Outputs als im Instruct-Modus. Die Symptome:
- 123s Inference fuer Salomo, Ergebnis: 5 Saetze
- Sokrates R2 wird komplett dupliziert (Rendering- oder Generierungs-Bug)
- Chinesische Zeichen lecken im Reasoning durch (各有优势, 您的)
- CoT kreist um Formatierung statt Inhalt

**Confirmed Finding:** "Reasoning efficiency matters more than reasoning volume."
Fuer kreative Multi-Agent-Debatten ist der Instruct-Modus klar ueberlegen.

### 2. Qwen3-235B: Qualitaetswunder trotz Q2-Quantisierung

Ueberraschendstes Ergebnis: Qwen3-235B bei aggressiver Q2_K_XL Quantisierung liefert
die hoechste Sprachqualitaet aller getesteten Modelle (nur 1 Tippfehler im gesamten Tribunal).
Philosophische Tiefe und Kreativitaet sind auf hoechstem Niveau.
Einziges Problem: Die Geschwindigkeit (2,8-5,5 tok/s, 20 min Tribunal-Dauer) macht es
fuer interaktive Nutzung unbrauchbar.

**Finding:** "Groessere Modelle mit aggressiver Quantisierung koennen kleinere Modelle
mit besserer Quantisierung in der Textqualitaet uebertreffen."

### 3. Quality/Speed-Ratio: Qwen3-Next Instruct ist der Sweet Spot

| Modell | Qualitaet (1-5) | Speed (tok/s) | Tribunal-Dauer | Quality/Speed |
|---|---|---|---|---|
| Qwen3-Next Instruct | 5 | 35,3 -> 20,8 | 2,5 min | Bester Kompromiss |
| Qwen3-235B | 5 | 5,5 -> 2,8 | 20 min | Hoechste Qualitaet, unbrauchbar langsam |
| GPT-OSS Q8 | 4 | 49,7 -> 44,9 | 1,9 min | Schnellstes Modell, gute Qualitaet |
| MiniMax Q2 | 2 | 7,9 -> 5,1 | 12 min | Langsam UND Qualitaetsprobleme |
| Qwen3 Thinking | 2 | 44,1 -> 42,9 | 6,2 min | Schnell, aber Thinking kontraproduktiv |

### 4. CPU-Offload-Penalty: Dramatischer Speed-Verlust

Modelle mit CPU-Offload (MiniMax ngl=48, Qwen3-235B ngl=73) zahlen einen enormen Preis:

| Metrik | GPU-only (Beste) | CPU-Offload (Beste) | Faktor |
|---|---|---|---|
| TTFT (Start) | 1,89s | 29,96s | 16x |
| TTFT (Ende) | 5,09s | 87,21s | 17x |
| TG (Start) | 49,7 tok/s | 7,9 tok/s | 6x |
| TG (Ende) | 44,9 tok/s | 5,1 tok/s | 9x |
| Tribunal gesamt | 1,9 min | 12 min | 6x |

### 5. Persona-Konsistenz: Drei-Agenten-Qualitaet korreliert mit Modellgroesse

Auffaellig: Alle Modelle halten AIfred (Butler) am konsistentesten.
Sokrates variiert stark -- bei Qwen3-Next Instruct und Qwen3-235B genuinely sokratisch,
bei MiniMax und GPT-OSS eher Debattier-Template.
Salomo ist der haerteste Test: Nur Qwen3-Next Instruct und Qwen3-235B liefern echte
richterliche Synthesen. GPT-OSS erstellt ein Scoring-Modell (kreativ, aber unsalomonisch).
MiniMax und Qwen3-Thinking produzieren generische "beide haben recht"-Zusammenfassungen.

### 6. Dense vs. MoE: Quantisierungstoleranz fundamental verschieden

GLM-4.7-REAP (Dense, IQ3_XXS) ist bei ~3 Bit/Gewicht komplett unbrauchbar, waehrend
Qwen3-235B (MoE, Q2_K_XL) bei ~2 Bit/Gewicht fast fehlerfrei funktioniert.
Die Ursache: Bei MoE werden pro Token nur 9-17% der Gewichte aktiviert, der Rest bleibt
inaktiv — Quantisierungsfehler in inaktiven Experten wirken sich nicht aus.
Bei Dense-Modellen akkumulieren die Fehler ueber alle Gewichte.

**Finding:** "MoE-Architekturen sind inherent quantisierungsresistenter als Dense-Modelle.
Ein Q2-MoE kann einen Q4-Dense in der Sprachqualitaet uebertreffen."

### 7. Multilingual-Kontamination korreliert mit Quantisierung

| Modell | Quant | CN-Leak | RU-Leak | EN-Leak | Gesamt |
|---|---|---|---|---|---|
| GPT-OSS Q8_0 | Q8_0 | Nein | Nein | Gering (gewollt) | Sauber |
| Qwen3-Next Q4_K_M (Instruct) | Q4_K_M | Nein | Nein | Gering (gewollt) | Sauber |
| Qwen3-Next Q4_K_M (Thinking) | Q4_K_M | Ja (im CoT) | Nein | Nein | Mittel |
| MiniMax Q2_K_XL | Q2_K_XL | Ja (im Output!) | Ja (im Output!) | Ja | Schwer |
| Qwen3-235B Q2_K_XL | Q2_K_XL | Nein | Nein | Nein | Sauber |

Bemerkenswerter Ausreisser: Qwen3-235B bei Q2 zeigt KEINE Fremdsprach-Kontamination,
waehrend MiniMax bei gleicher Quantisierungstiefe stark betroffen ist.
Dies deutet auf besseres multilinguales Alignment des Qwen3-Trainings hin.

---

## Herausragende Debattendynamiken

### Qwen3-Next Instruct: Emotionale Eskalation

Die Debatte entwickelt sich von spielerischem Vergleich zu existenzieller Selbstbefragung:
1. **AIfred R1:** Leichter Humor ("Katze ignoriert Sie, bis Sie Kasse machen")
2. **Sokrates R1:** Anthropomorphe Projektion aufgedeckt (Liebe als Instinkt)
3. **AIfred R2:** Philosophische Verteidigung (Ursache ≠ Bedeutung)
4. **Sokrates R2:** Psychologischer Tiefschlag ("Du brauchst einen Hund, weil du Angst hast, allein zu sein")
5. **Salomo:** Versoehnliche Synthese ("Ein Mensch, der beide lieben kann")

Diese Eskalationskurve ist bei keinem anderen Modell so ausgepraegt.

### Qwen3-235B: Philosophische Breite

Einziges Modell, das kulturuebergreifende philosophische Konzepte einbringt:
- Griechisch: arete, eudaimonia, logos, autarkia, synzygia
- Latein: contemplatio, virtus
- Hebraeisch: Tikkun (Welt-Reparatur durch Beziehung), Chochma (Weisheit)
- Soziologie: Domestikation als Entfremdung (Rousseau-Echo)

### GPT-OSS: Systematische Tiefe

Einziges Modell, das quantitative Argumente einfuehrt:
- CO2-Bilanzen, Futterverbrauch, Wasserverbrauch (allerdings mit Faktenfehlern)
- Studienreferenzen (teilweise halluziniert)
- Gewichtetes Scoring-Modell als Entscheidungshilfe
- Biodiversitaets-Argument gegen Freigaenger-Katzen

---

## Showcase-Struktur (geplant)

### Deutsche Version
- Deutsche Inferenzen (5 Sessions, alle aktuell)
- Deutsche Analyse (dieses Dokument)
- TTS-Demo einer Session (XTTS/MOSS-TTS)

### Englische Version
- Englische Inferenzen (separat, keine Uebersetzung)
- Englische Analyse
- TTS-Demo derselben Session auf Englisch

### Zusatz-Analyse
- Deutsch vs. Englisch Qualitaetsvergleich
- Sprachliche Unterschiede, Persona-Konsistenz ueber Sprachen hinweg

### Reddit-Post
- Kurzer, knackiger Post mit Highlights
- Link zum GitHub.io Showcase fuer Details
- Hervorhebung der Neuerungen:
  - TTS-Integration (MOSS-TTS, XTTS)
  - Tribunal-Modus (Multi-Agent-Debatte)
  - Autoscan & Kalibrierung fuer lokale Modelle
  - Hardware-Benchmarks auf Prosumer-Setup

---

## Offene Punkte

- [x] Deutsche Inferenzen fuer alle 5 Modelle -- erledigt
- [x] HTML-Export aller 5 Sessions -- erledigt (data/html_preview/)
- [x] Deutsche Analyse -- erledigt (dieses Dokument)
- [ ] Audio-Generierung (TTS) fuer beste Session(s)
- [ ] Englische Inferenzen fuer alle 5 Modelle
- [ ] TTS-Rendering einer Session (DE + EN)
- [ ] Deutsch/Englisch-Kreuzvergleich
- [ ] Showcase-HTML erstellen (DE + EN)
- [ ] Reddit-Post verfassen

---

## 🆕 Update 2026-02-21: 200B+ Model Optimizations

### Direct-IO Performance

Alle Modelle jetzt mit `--direct-io` Flag:
- **Ladezeit:** 60-90s → **2 Sekunden** (~45x schneller!)
- **Vorteil:** Umgeht CPU-RAM Page-Cache, füllt VRAM direkt
- **Funktioniert mit:** ext4, xfs, btrfs Dateisystemen

### KV-Quantisierung

| Modell | Original | Neu | Grund |
|--------|----------|-----|-------|
| GPT-OSS-120B | f16 | **f16** | Beibehalten (offiziell empfohlen) |
| Qwen3-Next-80B | f16 | **f16** | Beibehalten (Hybrid-Architektur) |
| MiniMax-M2.5 | q4_0 | **q4_0** | Beibehalten (q8_0 = OOM) |
| Qwen3-235B | q4_0 | **q4_0** | Beibehalten (q8_0 = OOM) |
| GLM-4.7-REAP | q8_0 | **q4_0** | **Geändert!** (q8_0 = OOM) |

### Batch-Größen-Optimierung

| Modell | Original | Neu | Grund |
|--------|----------|-----|-------|
| GPT-OSS-120B | 2048/2048 | **512/512** | VRAM-Engpass |
| Qwen3-Next-80B | 512/256 | **512/256** | Beibehalten |
| MiniMax-M2.5 | 4096/4096 | **1024/512** | **Geändert!** (4096 = OOM) |
| Qwen3-235B | 512/256 | **1024/512** | **Geändert!** (höher möglich) |
| GLM-4.7-REAP | 2048/512 | **2048/512** | Beibehalten |

### Stress-Tests Bestanden

Alle 200B+ Modelle stabil mit 130-200 Tokens:
- ✅ **Qwen3-235B-A22B:** 160 Tokens, VRAM: 43,5+21,4 GB
- ✅ **GLM-4.7-REAP-218B:** 130 Tokens, VRAM: 42+21 GB
- ✅ **MiniMax-M2.5:** 200 Tokens, VRAM: 42+20,4 GB

### Dokumentation

- 📄 [docs/model-recommended-params.md](model-recommended-params.md) - Deutsch
- 📄 [docs/model-recommended-params.en.md](model-recommended-params.en.md) - Englisch

## Datenquellen

- Session-JSONs (data/sessions/) werden fuer den Showcase NICHT benoetigt
- HTML-Previews (data/html_preview/) enthalten alle relevanten Metriken pro Bubble:
  TTFT, PP (tok/s), TG (tok/s), Inference-Zeit, Source (Agent + Modell + Backend)

### Dateizuordnung

| Datei | Modell |
|---|---|
| Hund_vs._Katze_Vor-_und_Nachteile.html | GPT-OSS-120B Q8_0 |
| Hund_oder_Katze_welcher_ist_besser.html | Qwen3-Next-80B-A3B Instruct Q4_K_M |
| Hund_oder_Katze_Vergleich.html | Qwen3-Next-80B-A3B Thinking Q4_K_M |
| Hund_oder_Katze.html | MiniMax-M2.5 Q2_K_XL |
| Hund_oder_Katze_Der_Vergleich.html | Qwen3-235B-A22B Instruct Q2_K_XL |
