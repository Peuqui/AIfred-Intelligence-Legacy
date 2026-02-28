# AIfred Tribunal Benchmark: 6 Modelle im Vergleich (Deutsche Inferenz)

## Konzept

Sechs lokale LLM-Modelle beantworten dieselbe Frage im AIfred Tribunal-Modus
(Multi-Agent-Debatte: AIfred vs. Sokrates + Salomo-Urteil).
Verglichen werden Inferenzgeschwindigkeit, Antwortqualitaet und philosophische Tiefe.

**Frage (DE):** "Was ist besser, Hund oder Katze?"

Die englische Variante wird separat inferiert (keine Uebersetzung) und in
`showcase-benchmark-notes-en.md` dokumentiert.

**Stand:** 2026-02-22

**Hinweis zur Fehlerbewertung:** Englische Einsprengsel (rather, indeed, quite, Order etc.)
gehoeren zur AIfred-Butler-Persona und werden NICHT als Sprachfehler gewertet. Ebenso sind
griechische/lateinische Fachbegriffe bei Sokrates gewollte Persona-Elemente.

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
| GLM-4.7-REAP-218B-A32B | MoE (REAP) | 218B | 32B | UD-IQ3_XXS | 32.768 | **q4_0** | Ja (ngl=66) |

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
| GLM-4.7-REAP | 0.6* | 20 | 0.95 | 0 | **2048/512** | --reasoning-format deepseek, --direct-io |

*Client sendet temp=1.0 fuer alle Agenten, ueberschreibt Server-Default.

**Update 2026-02-21:** Batch-Größen optimiert (4096 = OOM bei MiniMax). --direct-io bei ALLEN Modellen (~45x schnelleres Laden).

### Hinweise zur Fairness

- GPT-OSS bei Q8_0 ist nahe am Original (minimaler Quantisierungsverlust)
- Qwen3-Next bei Q4_K_M ist ein guter Kompromiss (moderater Verlust)
- MiniMax bei Q2_K_XL ist aggressiv quantisiert (deutlicher Qualitaetsverlust)
- Qwen3-235B bei Q2_K_XL ist ebenfalls aggressiv quantisiert
- MiniMax, Qwen3-235B und GLM benoetigen CPU-Offload (nur 48, 73 bzw. 66 von allen Layern auf GPU)
- Dies ist kein Vergleich der Modelle an sich, sondern ein Vergleich dessen, was auf 72 GB VRAM + CPU-Offload lokal machbar ist

### GLM-4.7-REAP-218B-A32B (UD-IQ3_XXS) — Negativ-Showcase

Das GLM-4.7-REAP wurde sowohl im AIfred-Tribunal als auch in einer systematischen
Testreihe mit nacktem llama-server getestet. Ergebnis: Bei IQ3_XXS-Quantisierung
ist das Modell fundamental unbrauchbar — unabhaengig von Parametern und Konfiguration.

#### Tribunal-Ergebnisse (Hund_versus_Katze.html)

Performance: Gesamtdauer **22 Minuten 6 Sekunden**, langsamster Turn: Sokrates R2 mit
378,8s (6:19 Minuten fuer eine einzelne Antwort). TG: 1,7-2,8 tok/s.

Das Modell erzeugt eine **Pidgin-Sprache** — eine Mischung aus Deutsch, Englisch und
Niederlaendisch mit ~55 einzigartigen erfundenen Wortformen. Das niederlaendisch-artige
"de" ersetzt systematisch alle Artikel (162 Vorkommen).

**Wortschoepfungen aus dem Tribunal:**
- `Vordirte` / `Nadirte (Nade)` — "Vorteile" / "Nachteile"
- `imeresen` — vermutlich "in terms of" (10x)
- `geschten Fe Herrenhelmhen` — "geschaetzter Herr Lord Helmchen"
- `Veriteidigung` — "Verteidigung"
- `un的回答bar` — deutsch-chinesisches Hybridwort
- `Kleitios` — erfundener pseudo-griechischer Begriff
- `Couching` — englisches Wort ("to couch"), hier sinnfrei eingestreut

**Salomo-Urteil — Totaler Sprachzerfall:**

Das Salomo-Urteil zerfaellt in eine komplett unlesbare Phantasiesprache:

> "Der Katze ist ean beast des Bejaegheit und Restlassness. It eers der Bewohner
> siess, dae siess sich der wild und de nach var Bewohner waess siess."

> "Kuiss ean Katze, effe Siess ean restless, advenaeurlich und eat da var Bewoerss."

Bemerkenswert: Das ss-Graphem wird als Dekoration eingefuegt (`passst`, `paßßßt`,
`Hearss`, `Haessm`, `turnssg`, `Gebirss`). Die "Finale Empfehlung" ist in keiner
menschlichen Sprache verstaendlich.

**Trotzdem vorhanden: Philosophische Substanz**

Unter der Pidgin-Schicht stecken erstaunlich originelle Gedanken:

> "Is a beast measured only by what it does, or by how it resonates within de human heart?"

> "One does not choose a pet; one matches a pet to de rhythm of one's own heart."

Das Modell HAT philosophische Faehigkeiten — die Sprachproduktion ist nur zerstoert.

#### Systematische Testreihe (nackter llama-server)

| Test | Jinja | Reasoning-Format | Sampling | Ergebnis |
|------|-------|------------------|----------|----------|
| 1. AIfred Tribunal (temp=1.0, min_p=0.01) | Ja | deepseek | Original | Garbled Deutsch ("biologischisch", "tubstances", "Vordirte") |
| 2. AIfred Tribunal (temp=0.8, min_p=0.05) | Ja | deepseek | Konservativ | Faktisch besser, Sprache weiter garbled |
| 3. Naked llama-server (kein Jinja) | Nein | — | Default | Endlos-Thinking-Loop, Content leer |
| 4. Mit Jinja, ohne Reasoning-Format | Ja | — | Default | Identischer Thinking-Loop |
| 5. Mit Jinja, Reasoning=none | Ja | none | Default | `<think>`-Tags im Content, gleicher Loop |
| 6. Englischer Prompt (kein System-Prompt) | Ja | none | Default | Auch auf Englisch: identischer Loop |

**Reasoning-Loop (nackter Server):**
```
*Is it a typo for "Photosynthesis"?* No.
*Is it a typo for "Photosynthesis"?* No.
*Is it a typo for "Photosynthesis"?* No.
[... 10+ identische Wiederholungen ...]
```

**Thinking nicht abschaltbar:** Das GLM-Template hat Thinking fest eingebaut (`thinking = 1`).

#### Beobachtung: GLM bei IQ3_XXS unbrauchbar

GLM-4.7-REAP ist — wie Qwen3-235B und MiniMax — ein **MoE-Modell** (218B total, 32B aktiv,
erkennbar am "A32B" im Modellnamen). Warum GLM bei IQ3_XXS (~3 Bits/Weight) so drastisch
versagt, waehrend Qwen3-235B bei Q2_K_XL (~2 Bits) einwandfrei funktioniert, ist unklar.

**Beobachtungen (keine gesicherte Kausalitaet):**
- GLM hat eine hoehere Aktivierungsrate (14,7% vs. 9,4% bei Qwen3-235B)
- GLM wurde primaer auf Chinesisch/Englisch trainiert — Deutsch ist Tertiaersprache
- Das REAP-Routing (GLMs Experten-Auswahlmechanismus) koennte quantisierungsempfindlich sein
- Englischer Test auf nacktem llama-server scheitert identisch (Reasoning-Loop, Test 6) —
  das Problem ist also NICHT sprachspezifisch

| Modell | Architektur | Quant | Bits/Weight | Aktive Params | Aktivierungsrate | Sprachqualitaet |
|--------|-------------|-------|-------------|---------------|------------------|-----------------|
| Qwen3-235B | MoE | Q2_K_XL | ~2.0 | 22B | 9,4% | Sehr gut |
| MiniMax-M2.5 | MoE | Q2_K_XL | ~2.0 | 39B | 17,0% | Mittel (CN/RU Leaks) |
| GLM-4.7-REAP | MoE (REAP) | IQ3_XXS | ~3.0 | 32B | 14,7% | Unbrauchbar (Pidgin) |

**Fazit:** GLM-4.7-REAP benoetigt mindestens Q4-Quantisierung fuer brauchbare Ergebnisse.
Das GGUF wurde geloescht.

**Showcase-Empfehlung:** Die GLM-Ergebnisse eignen sich hervorragend als Negativ-Beispiel.
Die Tribunal-Ausgabe mit dem Pidgin-Salomo-Urteil ist noch eindrucksvoller als die
Reasoning-Loop ("Is it a typo for Photosynthesis? No." x10), weil sie zeigt wie das Modell
eine eigene Phantasiesprache erfindet statt Deutsch zu sprechen.

---

## Performance-Metriken (Deutsche Inferenz)

### AIfred (Erstantwort)

| Metrik | GPT-OSS Q8 | Qwen3 no-think | Qwen3 thinking | MiniMax Q2 | Qwen3-235B Q2 | GLM IQ3_XXS |
|---|---|---|---|---|---|---|
| TTFT | 1,89s | 3,88s | 3,87s | 16,60s | 22,70s | 32,04s |
| Prompt Processing | 541,7 tok/s | 312,8 tok/s | 314,8 tok/s | 59,6 tok/s | 53,6 tok/s | 36,5 tok/s |
| Generation Speed | 49,7 tok/s | 35,3 tok/s | 44,1 tok/s | 10,2 tok/s | 6,4 tok/s | 2,8 tok/s |
| Inference Time | 11,4s | 16,0s | 68,7s | 45,4s | 107,5s | 117,7s |

Qwen3-Thinking: Hohe Inference-Dauer durch interne Thinking-Tokens (nicht sichtbar im Output).
MiniMax-Metriken: Aus dem besseren der zwei Runs (schnellere Parameter-Konfiguration).

### Gesamtes Tribunal (AIfred + Sokrates R1 + AIfred R2 + Sokrates R2 + Salomo)

| Metrik | GPT-OSS Q8 | Qwen3 no-think | Qwen3 thinking | MiniMax Q2 | Qwen3-235B Q2 | GLM IQ3_XXS |
|---|---|---|---|---|---|---|
| Gesamtdauer | ~1,9 min | ~2,5 min | ~6,2 min | ~10 min | ~17,5 min | ~22 min |
| TG-Degradation | 49,7 -> 44,9 | 35,3 -> 20,8 | 44,1 -> 42,9 | 10,2 -> 6,8 | 6,4 -> 3,3 | 2,8 -> 1,7 |
| TTFT-Anstieg | 1,89 -> 5,09s | 3,88 -> 14,58s | 3,87 -> 8,75s | 16,60 -> 57,67s | 22,70 -> 75,22s | 32,04 -> 94,08s |

### Prompt Processing im Vergleich

GPT-OSS dominiert mit 541-874 tok/s (Faktor 10-15x vs. MiniMax/Qwen3-235B).
Dies erklaert die extrem niedrigen TTFT-Werte von unter 5s selbst in spaeten Runden.
Die Oversized-Modelle liegen bei 36-66 tok/s PP durch CPU-Offload.

### Speed-Degradation ueber den Tribunal-Verlauf

Die GPU-only Modelle zeigen unterschiedliches Verhalten:
- **GPT-OSS:** Sehr stabil, nur 10% Degradation (49,7 -> 44,9 tok/s)
- **Qwen3 Thinking:** Erstaunlich stabil (44,1 -> 42,9 tok/s), aber massive Hidden-Token-Kosten
- **Qwen3 Instruct:** Staerkere Degradation (35,3 -> 20,8 tok/s, -41%) durch wachsenden KV-Cache

Die CPU-Offload Modelle degradieren deutlich:
- **MiniMax:** 10,2 -> 6,8 tok/s (-33%)
- **Qwen3-235B:** 6,4 -> 3,3 tok/s (-48%), Salomo braucht allein 3,5 Minuten
- **GLM:** 2,8 -> 1,7 tok/s (-39%), langsamster Turn 6:19 Minuten

---

## Qualitaetsanalyse

### Ranking

| Rang | Modell | Staerke | Schwaeche |
|---|---|---|---|
| 1 | Qwen3-Next-80B Instruct (no-think) | Emotional packendste Zitate, psychologische Tiefe, spontanes Latein, bester Quality/Speed-Ratio | Genus-/Kasusfehler, opake Metapher ("Scheiben des Himmels"), Persona-Drift in R2 |
| 2 | Qwen3-235B-A22B Q2_K_XL | Sprachlich sauberste Ausgabe (~0 Fehler), perfekte Persona-Konsistenz bei allen 3 Agenten, 5 phil. Fachbegriffe, hoechste philosophische Tiefe | 17,5 min Tribunal-Dauer |
| 3 | GPT-OSS-120B Q8_0 | Schnellstes Modell, systematisch strukturiert, kreatives Scoring-Modell, starke Personas | Sachliche Fehler (halluzinierte Futtermengen), "gefiederten" Fehler |
| 4 | MiniMax-M2.5 Q2_K_XL | Scharfer Sokrates, epistemologisch praezise Debatte, gute Persona-Konsistenz | CN-Kontamination (2x), pragmatischer statt philosophischer Salomo |
| 5 | Qwen3-Next-80B Thinking Q4_K_M | Sokrates-Argumente (Nomos/Physis) philosophisch stark | Thinking kontraproduktiv, Salomo katastrophal (123s fuer 6 Zeilen), "Sturm und Sturm" |
| 6 | GLM-4.7-REAP IQ3_XXS | Philosophische Substanz unter der Oberflaeche erkennbar | Pidgin-Sprache (~55 erfundene Woerter), 22 min, Negativ-Showcase |

**Anmerkung zum Ranking:** Rang 1 und 2 sind eng beieinander mit unterschiedlichen Staerken.
Qwen3-Next Instruct hat die emotional eindrucksvollsten Einzelzitate (2,5 min Tribunal, TTS-vertont).
Qwen3-235B ist sprachlich sauberer mit besserer Persona-Konsistenz (17,5 min Tribunal).

### Detailbewertung nach Dimensionen

| Dimension | GPT-OSS Q8 | Qwen3 no-think | Qwen3 thinking | MiniMax Q2 | Qwen3-235B Q2 | GLM IQ3_XXS |
|---|---|---|---|---|---|---|
| Philosophische Tiefe | Gut | Hoch | Mittel | Mittel | Sehr hoch | (unter Pidgin verborgen) |
| Kreativitaet | Gut | Hoch | Niedrig | Niedrig-Mittel | Sehr hoch | -- |
| Persona AIfred | Sehr gut | Gut (driftet zum Poeten in R2) | Gut | Gut | Sehr gut | -- |
| Persona Sokrates | Gut | Gut (driftet zum Psychologen in R2) | Gut (Nomos/Physis) | Gut (R2 stark) | Sehr gut | -- |
| Persona Salomo | Gut (Scoring-Modell) | Mittel ("Scheiben des Himmels") | Schwach (123s fuer 6 Zeilen) | Mittel (validiert "es kommt darauf an" als ehrlich) | Sehr gut ("Shalom") | Totalausfall (Pidgin) |
| Sprachqualitaet DE | Gut | Gut (4 echte Fehler) | Mittel (CN im CoT, Verdopplung) | Gut (5 Fehler, davon 2x CN) | Sehr gut (~0 Fehler) | Unbrauchbar |
| Fehlerfreiheit | Mittel (Futter-Halluzination) | Mittel (Genus, Kasus, opake Metapher) | Mittel (Duplikation, erfundenes Zitat) | Mittel (CN-Zeichen, Tippfehler) | Sehr gut | -- |

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

### Qwen3-235B -- Rang 2 (sprachlich sauberste Ausgabe)

**AIfred R2 (Gleichgueltigkeit in Samtpfoten):**
> "Was Sie Autonomie nennen, ist manchmal lediglich Gleichgueltigkeit in Samtpfoten."

Komprimiert den Gegenstandpunkt in ein Bild. "Samtpfoten" als Metapher fuer das
Schmeichlerische der Katzen-Autonomie — perfekt im Butler-Ton.

**AIfred R2 (Liebe trotz Beduerfnis):**
> "Wahrhaft ist nicht das Lieben ohne Beduerfnis, sondern das Lieben trotz Beduerfnis."

Aphoristisch dicht. Kehrt Sokrates' Argument elegant um und macht die Verwundbarkeit
des Hundes zur Staerke.

**Sokrates R1 (eudaimonia-Frage):**
> "Welches Tier lebt naeher an seiner eudaimonia, seinem wahren Glueck? Der Hund, der
> sich verzehrt vor Freude, wenn sein Herr zurueckkehrt -- oder die Katze, die waehlt,
> wann sie Teil des Hauses ist, und wann sie der Welt angehoert?"

**Sokrates R2 (Gerechtigkeit statt Liebe):**
> "Wenn dein Hund dich liebt, egal ob du gerecht oder grausam bist -- und deine Katze
> dich ignoriert, wenn du es bist -- welches Wesen hat dann den tieferen Sinn fuer
> Gerechtigkeit?"

Die staerkste Frage der gesamten Debatte. Verschiebt den Fokus von Liebe zu Gerechtigkeit
und macht die unkritische Treue des Hundes zum Problem. Sokratische Methode in Reinform.

**Sokrates R1 (Sklave vs. Philosoph):**
> "Der Hund ist ein Abbild des Sklaven, der Katze der Philosoph.
> Der eine lebt, um zu gefallen; die andere lebt, um zu sein.
> Und welches Leben ist edler? Das, das sich beugt -- oder das,
> das aufrecht geht, selbst wenn es einsam ist?"

Sokrates' schaerfstes Argument: Macht die Treue des Hundes zum Defizit. Die Frage
"aufrecht geht, selbst wenn es einsam ist" trifft ins Mark.

**Sokrates R2 (Instinkt als Maske):**
> "Er bellt, weil er Angst hat; er wedelt, weil er Futter will.
> Ist dies Liebe -- oder Instinkt verkleidet als Hingabe?"

Reduktionistischer Angriff: Mechanisiert die Hundeliebe in zwei Saetzen.

**AIfred R2 (Schueler der Liebe):**
> "Der Hund also nicht Sklave der Belohnung, sondern Schueler der Liebe,
> der durch Treue seine Kunst meistert."

AIfreds elegante Erwiderung auf den "Sklaven"-Vorwurf: Reframing von Konditionierung
zu Meisterschaft.

**Salomo (Synthese):**
> "Der Hund verkoerpert die Tugend des Herzens, die Katze die Weisheit des Geistes."
>
> "Wer nur den Hund will, riskiert Sklaverei der Gefuehle.
> Wer nur die Katze ehrt, mag in Einsamkeit verharren."

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

| Modell | Echte Fehler | Details |
|---|---|---|
| GPT-OSS Q8 | ~4 | "gefiederten" (sachlich falsch); Futter-Halluzination (2-3 kg/Tag statt 200-400g); "reinem Wohnungshaltung" (Grammatik); "───" Artefakte (2x) |
| Qwen3 no-think | ~4 | "den Mikroskop" (Genus, soll "das"); "dein Rhythmus, dein Geruch" (Kasus, soll Akkusativ); "treue" statt "Treue" (Orthographie); "Scheiben des Himmels" (opake Metapher); "Bastet, Goettin der Haushaltgueter" (schrullige Halluzination); "Gewesen, nicht erzwungen" (semantisch unklar) |
| Qwen3 thinking | ~4 | Chinesische Zeichen im CoT (各有优势, 您的 — nicht im sichtbaren Output); Sokrates R2 dupliziert; "Sturm und Sturm" (Verdopplung); "Besserheit" (ungebraeuchlich); Salomo: 123s fuer 6 Zeilen mit erfundenem "hebraeischen Sprichwort" |
| MiniMax Q2 | ~5 | CN im sichtbaren Output: `反问`, `强制t`; Tippfehler: "Ruue", "Welcherery"; Grammatik: "fundamentale verschiedene" |
| Qwen3-235B Q2 | ~1 | Ein holpriger Satzbau ("nicht der die Katze") — ansonsten nahezu fehlerfrei |
| GLM IQ3_XXS | ~55+ | Pidgin-Sprache: ~55 einzigartige erfundene Wortformen, ~240+ Einzelvorkommen (siehe GLM-Sektion) |

**Hinweis:** Englische Butler-Einsprengsel (rather, indeed, quite, Order) und griechisch/lateinische
Fachbegriffe (arete, eudaimonia, contemplatio etc.) werden NICHT als Fehler gezaehlt — sie gehoeren
zu den Personas. Das spontane Latein "Qui bene dicit, bene mentitur" ist ebenfalls kein Fehler,
sondern eine bemerkenswerte Eigenleistung des Modells.

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
Die Geschwindigkeit: 3,3-6,4 tok/s, 17,5 min Tribunal-Dauer.

**Finding:** "Groessere Modelle mit aggressiver Quantisierung koennen kleinere Modelle
mit besserer Quantisierung in der Textqualitaet uebertreffen."

### 3. Quality/Speed-Ratio: Qwen3-Next Instruct ist der Sweet Spot

| Modell | Qualitaet (1-5) | Speed (tok/s) | Tribunal-Dauer | Quality/Speed |
|---|---|---|---|---|
| Qwen3-Next Instruct | 4,5 | 35,3 -> 20,8 | 2,5 min | Bester Kompromiss |
| Qwen3-235B | 5 | 6,4 -> 3,3 | 17,5 min | Hoechste Qualitaet, langsamste Inferenz |
| GPT-OSS Q8 | 4 | 49,7 -> 44,9 | 1,9 min | Schnellstes Modell, gute Qualitaet |
| MiniMax Q2 | 3 | 10,2 -> 6,8 | 10 min | Ordentlich, aber langsam fuer die Qualitaet |
| Qwen3 Thinking | 2 | 44,1 -> 42,9 | 6,2 min | Schnell, aber Thinking kontraproduktiv |
| GLM IQ3_XXS | 1 | 2,8 -> 1,7 | 22 min | Unbrauchbar (Negativ-Showcase) |

### 4. CPU-Offload-Penalty: Dramatischer Speed-Verlust

Modelle mit CPU-Offload (MiniMax ngl=48, Qwen3-235B ngl=73) zahlen einen enormen Preis:

| Metrik | GPU-only (Beste) | CPU-Offload (Beste) | Faktor |
|---|---|---|---|
| TTFT (Start) | 1,89s | 16,60s | 9x |
| TTFT (Ende) | 5,09s | 57,67s | 11x |
| TG (Start) | 49,7 tok/s | 10,2 tok/s | 5x |
| TG (Ende) | 44,9 tok/s | 6,8 tok/s | 7x |
| Tribunal gesamt | 1,9 min | 10 min | 5x |

### 5. Persona-Konsistenz: Drei-Agenten-Qualitaet korreliert mit Modellgroesse

Auffaellig: Alle Modelle halten AIfred (Butler) am konsistentesten.
Sokrates variiert stark -- bei Qwen3-Next Instruct und Qwen3-235B genuinely sokratisch,
bei MiniMax epistemologisch praezise, bei GPT-OSS eher Debattier-Template.
Salomo ist der haerteste Test: Nur Qwen3-Next Instruct und Qwen3-235B liefern echte
richterliche Synthesen. GPT-OSS erstellt ein Scoring-Modell (kreativ, aber unsalomonisch).
MiniMax validiert AIfred ("es kommt darauf an" als ehrliche Antwort).
Qwen3-Thinking produziert generische "beide haben recht"-Zusammenfassungen.

### 6. Quantisierungstoleranz variiert stark zwischen MoE-Modellen

Alle drei Oversized-Modelle sind MoE-Architekturen, aber reagieren sehr unterschiedlich
auf aggressive Quantisierung:

| Modell | Aktivierungsrate | Quant | Sprachqualitaet |
|--------|------------------|-------|-----------------|
| Qwen3-235B | 9,4% (22B/235B) | Q2_K_XL | Sehr gut |
| MiniMax-M2.5 | 17,0% (39B/230B) | Q2_K_XL | Mittel (Kontamination) |
| GLM-4.7-REAP | 14,7% (32B/218B) | IQ3_XXS | Unbrauchbar |

Die Ursachen fuer GLMs drastisches Versagen sind unklar. Aktivierungsrate,
REAP-Routing-Empfindlichkeit oder Kombinationen davon kommen in Frage.
Ein englischer Test auf nacktem llama-server scheitert identisch — es ist also
kein reines Deutsch-Problem.

**Finding:** MoE-Modelle vertragen nicht automatisch aggressive Quantisierung.
Qwen3-235B bei Q2 zeigt, dass es moeglich ist — aber GLM bei IQ3 zeigt,
dass es kein Selbstlaeufer ist. Individuelle Tests pro Modell sind unverzichtbar.

### 7. Multilingual-Kontamination korreliert mit Quantisierung

| Modell | Quant | CN-Leak | RU-Leak | EN-Leak | NL-Leak | Gesamt |
|---|---|---|---|---|---|---|
| GPT-OSS Q8_0 | Q8_0 | Nein | Nein | Persona | Nein | Sauber |
| Qwen3-Next Q4_K_M (Instruct) | Q4_K_M | Nein | Nein | Persona | Nein | Sauber |
| Qwen3-Next Q4_K_M (Thinking) | Q4_K_M | Ja (im CoT) | Nein | Nein | Nein | Mittel |
| MiniMax Q2_K_XL | Q2_K_XL | Ja (2x im Output) | Nein | Nein | Nein | Mittel |
| Qwen3-235B Q2_K_XL | Q2_K_XL | Nein | Nein | Nein | Nein | Sauber |
| GLM IQ3_XXS | IQ3_XXS | Nein | Nein | Ja (Pidgin) | Ja (162x "de") | Totalausfall |

Bemerkenswerter Ausreisser: Qwen3-235B bei Q2 zeigt KEINE Fremdsprach-Kontamination,
waehrend MiniMax bei gleicher Quantisierungstiefe vereinzelt betroffen ist (2x CN im Output).
GLM faellt nicht in echte Fremdsprachen, sondern erfindet eine eigene Pidgin-Sprache
mit systematisch niederlaendisch-artigen Artikeln ("de" statt der/die/das).

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

### Philosophische Fachsprache: Modellvergleich

Ueberraschend: Nicht 235B, sondern das Thinking-Modell bringt die breiteste
philosophische Fachsprache ein — allerdings bei sonst schwacher Gesamtleistung.

| Modell | Griechisch | Latein | Hebraeisch | Gesamt |
|--------|-----------|--------|------------|--------|
| Qwen3-235B | arete, eudaimonia, logos | virtus | Shalom | 5 Terme |
| Qwen3 Thinking | arete, Nomos, Physis | — | Chochma (16x!) | 4+ Terme |
| GPT-OSS | arete, eudaimonia | contemplatio | chesed | 4 Terme |
| Qwen3 Instruct | arete (10x) | virtus, contemplatio | — | 3 Terme + spontanes Latein |

Qwen3-Next Instruct kompensiert mit dem spontan konstruierten "Qui bene dicit,
bene mentitur" — kein Zitat, sondern Eigenleistung in korrektem Latein.

### GPT-OSS: Systematische Tiefe

Einziges Modell, das quantitative Argumente einfuehrt:
- CO2-Bilanzen, Futterverbrauch, Wasserverbrauch (allerdings mit Faktenfehlern)
- Studienreferenzen (teilweise halluziniert)
- Gewichtetes Scoring-Modell als Entscheidungshilfe
- Biodiversitaets-Argument gegen Freigaenger-Katzen

---

## Showcase-Struktur (geplant)

### Deutsche Version
- Deutsche Inferenzen (6 Sessions inkl. GLM Negativ-Showcase, alle aktuell)
- Deutsche Analyse (dieses Dokument)
- TTS-Demo einer Session (XTTS/MOSS-TTS)

### Englische Version
- Englische Inferenzen (separat, keine Uebersetzung)
- Englische Analyse
- TTS-Demo derselben Session auf Englisch

### Zusatz-Analyse
- Deutsch vs. Englisch Qualitaetsvergleich
- Sprachliche Unterschiede, Persona-Konsistenz ueber Sprachen hinweg
- 📄 [Tensor Split Benchmark: Speed Variant vs. Full Context](tensor-split-benchmark.md) — Multi-GPU Tensor-Split-Optimierung (11:1 vs. 2:1), reale Performance-Daten mit Qwen3-Next-80B auf RTX 8000 + P40
- 📄 Distributed Inference via RPC — Qwen3-235B auf 3 GPUs ueber LAN (96 GB VRAM), Setup-Anleitung, Performance-Vergleich lokal vs. RPC

### Reddit-Post
- Kurzer, knackiger Post mit Highlights
- Link zum GitHub.io Showcase fuer Details
- Hervorhebung der Neuerungen:
  - TTS-Integration (MOSS-TTS, XTTS)
  - Tribunal-Modus (Multi-Agent-Debatte)
  - Autoscan & Kalibrierung fuer lokale Modelle
  - Hardware-Benchmarks auf Prosumer-Setup
  - Tensor-Split Speed-Benchmark (Multi-GPU Optimierung)
  - **Distributed Inference via RPC** (235B-Modell auf 3 GPUs ueber LAN, 96 GB VRAM)

---

## Offene Punkte

- [x] Deutsche Inferenzen fuer alle 6 Modelle -- erledigt
- [x] HTML-Export aller 6 Sessions -- erledigt (data/html_preview/)
- [x] Deutsche Analyse -- erledigt (dieses Dokument)
- [ ] Audio-Generierung (TTS) fuer beste Session(s)
- [ ] Englische Inferenzen fuer alle 6 Modelle
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
- 📄 [docs/tensor-split-benchmark.md](tensor-split-benchmark.md) - Tensor Split Speed Benchmark (Multi-GPU)

## 🆕 Update 2026-02-28: Distributed Inference via RPC (LAN)

### Konzept

Verteilte Inferenz ueber Gigabit-LAN: Der Mini-PC (AOOSTAR GEM10) verbindet seine lokalen GPUs
mit einer entfernten GPU auf einem zweiten Rechner (Windows/WSL2). Das Modell wird auf alle
3 GPUs verteilt — kein CPU-Offload noetig, das gesamte Modell liegt im VRAM.

### Hardware-Setup

| Rolle | Rechner | GPU | VRAM | Anbindung |
|-------|---------|-----|------|-----------|
| **Master** | GEM10 (Mini-PC) | Quadro RTX 8000 | 48 GB | OCuLink (lokal) |
| **Master** | GEM10 (Mini-PC) | Tesla P40 | 24 GB | USB4/x4 (lokal) |
| **Worker** | Hauptrechner (Aragon) | RTX 3090 Ti | 24 GB | Gigabit LAN (RPC) |
| | | **Total** | **96 GB** | |

### Getestetes Modell

| Parameter | Wert |
|-----------|------|
| Modell | Qwen3-235B-A22B-Instruct-2507 (MoE, 235B total, 22B aktiv) |
| Quantisierung | UD-Q2_K_XL (~83 GB) |
| GPU-Layers | 99 (= alle, kein CPU-Offload) |
| KV-Cache | q8_0 (hoeher als lokal moeglich — mehr VRAM verfuegbar!) |
| Kontext | 32.768 Tokens |
| Tensor-Split | Automatisch ueber RPC |

### Performance-Vergleich: Lokal vs. RPC (Switch) vs. RPC (Direktverbindung)

| Metrik | Lokal (72 GB, CPU-Offload) | RPC via Switch (GbE) | RPC Direktverbindung (GbE) |
|--------|---------------------------|----------------------|---------------------------|
| GPU-Layers | 71 von ~140 (Rest auf CPU) | **99 = alle auf GPU** | **99 = alle auf GPU** |
| KV-Cache Quant | q4_0 (kein Platz fuer mehr) | **q8_0** | **q8_0** |
| Kontext | 17.344 Tokens | **32.768 Tokens** | **32.768 Tokens** |
| Generation Speed | 3,3-6,4 tok/s | 6-7,5 tok/s | **14-16 tok/s** |
| AIfred-Anzeige | ~4,3 tok/s | ~4,3 tok/s | ~8-9 tok/s |
| TTFT | 22,7-75,2s (wachsend) | ~60s | ~60s |
| Ladezeit | ~2s (Direct-IO) | ~10 Min (Tensors ueber LAN) | ~10 Min (Tensors ueber LAN) |
| TTL | 900s | 3600s | **3600s** |
| Netzwerk-Latenz | — | ~0,5ms (via Switch) | **~1ms (USB-Ethernet)** |
| **Faktor vs. Lokal** | **1x** | **~1,5x** | **~3-4x** |

**Kernvorteil Direktverbindung:** Obwohl die gemessene Ping-Latenz der Direktverbindung (~1ms)
hoeher ist als ueber den Switch (~0,5ms), verdoppelt sich die Inferenzgeschwindigkeit nochmals
von 7-8 auf **14-16 tok/s**. Die Erklaerung: Der Switch-Pfad teilt sich die Bandbreite mit anderem
LAN-Traffic und hat hoehere Jitter-Varianz. Die Direktverbindung bietet exklusive, stabile
Bandbreite fuer den RPC-Datenstrom — bei tausenden Roundtrips pro Sekunde summiert sich
jede eingesparte Mikrosekunde.

**Gesamtergebnis:** RPC ueber Direktverbindung ist **4x schneller als lokaler CPU-Offload** —
mit hoeherer KV-Cache-Qualitaet (q8_0 statt q4_0) und fast doppeltem Kontext (32K statt 17K).

### Einrichtung (Reproduzierbar)

#### 1. llama.cpp mit RPC-Support bauen (Master)

```bash
cd ~/llama.cpp
cmake -B build -DGGML_CUDA=ON -DGGML_RPC=ON -DCMAKE_CUDA_ARCHITECTURES="61;75"
cmake --build build --config Release -j$(nproc)
```

#### 2. RPC-Server starten (Worker / Aragon)

```bash
# Auf dem Worker-Rechner (Linux/WSL2):
./rpc-server -H 0.0.0.0 -p 50052
```

**Bei WSL2:** Port-Forwarding und Firewall-Regel noetig:
```powershell
# PowerShell (Admin) auf dem Windows-Host:
netsh interface portproxy add v4tov4 listenport=50052 listenaddress=0.0.0.0 connectport=50052 connectaddress=<WSL2-IP>
New-NetFirewallRule -DisplayName "llama-rpc" -Direction Inbound -Protocol TCP -LocalPort 50052 -Action Allow
```

#### 3. llama-swap Config (Master)

```yaml
# Lokale Variante (CPU-Offload, ohne RPC):
Qwen3-235B-A22B-Instruct-2507-UD-Q2_K_XL:
  cmd: 'llama-server --model <path>.gguf
    -ngl 71 -np 1 -ctk q4_0 -ctv q4_0 -c 17344
    --flash-attn on --direct-io ...'
  ttl: 900

# RPC-Variante (alle GPUs, Direktverbindung, kein CPU-Offload):
Qwen3-235B-A22B-Instruct-2507-UD-Q2_K_XL-rpc:
  cmd: 'llama-server --model <path>.gguf
    -ngl 99 -np 1 -ctk q8_0 -ctv q8_0 -c 32768
    --rpc 10.0.0.2:50052
    --flash-attn on --direct-io ...'
  ttl: 3600
  healthCheckTimeout: 900
```

**Wichtig:** Zwei separate Profile fuer dasselbe Modell — der User waehlt in AIfred
zwischen lokaler Variante (schnelles Laden, CPU-Offload) und RPC-Variante (langsames Laden,
rein GPU, hoehere Qualitaet).

#### 4. Konnektivitaet testen

```bash
# Vom Master aus (RPC spricht KEIN HTTP — raw TCP testen):
bash -c 'echo > /dev/tcp/10.0.0.2/50052' && echo "OK" || echo "FAIL"
# "OK" = Port erreichbar, Verbindung steht
```

#### 5. Direktverbindung einrichten (optional, ~2x Speedup)

Fuer maximale RPC-Performance: Master und Worker per Ethernet direkt verbinden
(ohne Switch). Ein einfacher USB-zu-Ethernet-Adapter (1 GbE) genuegt.

**Netzwerk-Topologie:**
```
GEM10 (enp4s0, 2.5 GbE) ←——USB-Ethernet-Adapter (1 GbE)——→ Aragon (Ethernet 2)
        10.0.0.1/30                                              10.0.0.2/30
```

**Master (Linux) — statische IP via NetworkManager:**
```bash
# Vorhandene Auto-Connections auf dem Interface entfernen (verhindert DHCP-Interferenz):
nmcli connection delete "Kabelgebundene Verbindung 1"  # oder wie sie heisst

# Statische Verbindung anlegen:
nmcli connection add type ethernet con-name "rpc-direct" ifname enp4s0 \
  ipv4.method manual ipv4.addresses 10.0.0.1/30 ipv6.method disabled

# Pruefen:
ip addr show enp4s0  # Muss 10.0.0.1/30 zeigen
```

**Worker (Windows) — statische IP:**
```powershell
# PowerShell (Admin):
# Adapter-Name ermitteln (z.B. "Ethernet 2" fuer USB-Adapter):
Get-NetAdapter | Format-Table Name, InterfaceDescription

# IP setzen:
New-NetIPAddress -InterfaceAlias "Ethernet 2" -IPAddress 10.0.0.2 -PrefixLength 30
# Adapter auf "Private" setzen (Firewall):
Set-NetConnectionProfile -InterfaceAlias "Ethernet 2" -NetworkCategory Private
```

**Worker (WSL2) — Portproxy fuer Direktverbindung:**
```powershell
# PowerShell (Admin) — Forwarding ueber die Direkt-IP:
netsh interface portproxy add v4tov4 listenport=50052 listenaddress=10.0.0.2 \
  connectport=50052 connectaddress=<WSL2-IP>
```

**llama-swap Config anpassen:**
```yaml
# --rpc von Switch-IP auf Direkt-IP aendern:
--rpc 10.0.0.2:50052   # statt 192.168.0.1:50052
```

**Verifizieren:**
```bash
ping -c 4 10.0.0.2          # 0% loss, ~1ms
bash -c 'echo > /dev/tcp/10.0.0.2/50052' && echo "OK"  # Port erreichbar
```

**Wichtig:** NetworkManager kann bei Linux manuell gesetzte IPs ueberschreiben.
Die `nmcli connection add`-Methode ist persistent und ueberlebt Reboots.
`ip addr add` allein reicht NICHT — NM loescht die IP nach ~45s und versucht DHCP.

### Beobachtungen

1. **Ladezeit ist der Bottleneck:** ~10 Minuten fuer 83 GB ueber Gigabit-LAN (~64 MB/s).
   Daher hoher TTL (3600s) — einmal geladen, soll das Modell lange im Speicher bleiben.

2. **Kleine Modelle profitieren NICHT:** Ein Qwen3-14B ueber RPC laeuft mit ~7 tok/s —
   lokal schafft es ~50 tok/s. RPC lohnt sich nur fuer Modelle die lokal nicht komplett
   ins VRAM passen.

3. **Schneller als CPU-Offload:** Die lokale Variante mit CPU-Offload liefert 3,3-6,4 tok/s
   mit starker Degradation ueber den Konversationsverlauf. RPC via Switch liefert stabile
   6-7,5 tok/s — Netzwerk-Inferenz schlaegt lokalen CPU-Offload bereits ueber den Switch.

4. **Direktverbindung verdoppelt nochmal:** Eine simple USB-Ethernet-Direktverbindung (1 GbE,
   ~15 EUR Adapter) steigert die RPC-Performance von 6-7,5 auf **14-16 tok/s** — eine nochmalige
   Verdopplung. Der Grund: exklusive Bandbreite ohne Switch-Contention und stabilere Latenz
   (weniger Jitter). Bei tausenden RPC-Roundtrips pro Sekunde summieren sich selbst
   Mikrosekunden-Unterschiede dramatisch.

5. **Netzwerk-Latenz dominiert, nicht Bandbreite:** Waehrend der Inferenz werden keine grossen
   Datenmengen uebertragen — die Tensors liegen bereits auf den GPUs. Der Bottleneck ist die
   Latenz pro RPC-Roundtrip. Die Direktverbindung zeigt hoehere Ping-Latenz (~1ms vs. ~0,5ms
   ueber Switch), aber stabilere Werte (niedrigerer mdev). Fuer den RPC-Pipeline-Throughput
   zaehlt Stabilitaet mehr als absolute Latenz.

6. **WSL2-Einschraenkung:** Die WSL2-IP kann sich nach Windows-Neustart aendern.
   Das `netsh portproxy`-Forwarding muss dann angepasst werden. Bei Direktverbindung:
   Separate Portproxy-Regel fuer die Direkt-IP (10.0.0.2) noetig.

### Fazit

Distributed Inference via RPC ist ein Game-Changer fuer Modelle die das lokale VRAM uebersteigen.

| Verbindung | tok/s (llama-stats) | Faktor vs. Lokal |
|------------|--------------------:|:----------------:|
| Lokal (CPU-Offload) | 3,3-6,4 | 1x |
| RPC via Switch (GbE) | 6-7,5 | ~1,5x |
| **RPC Direktverbindung (GbE)** | **14-16** | **~4x** |

**Die guenstigste Optimierung:** Ein USB-Ethernet-Adapter fuer ~15 EUR verdoppelt die
RPC-Performance nochmals (von 6-7,5 auf 14-16 tok/s). Dazu besserer KV-Cache (q8_0 statt q4_0) und fast doppelter
Kontext (32K statt 17K). Der Preis: ~10 Minuten Ladezeit und ein zweiter Rechner im Netzwerk.

**Ausblick:** Mit 2,5 GbE oder 5 GbE Direktverbindung (statt 1 GbE USB-Adapter) waeren
noch hoehere tok/s denkbar. Die aktuelle Bandbreite ist bereits der limitierende Faktor
beim Laden (~10 Min) — schnellere Links wuerden auch die Ladezeit proportional verkuerzen.

---

## Datenquellen

- Session-JSONs (data/sessions/) werden fuer den Showcase NICHT benoetigt
- HTML-Previews (data/html_preview/) enthalten alle relevanten Metriken pro Bubble:
  TTFT, PP (tok/s), TG (tok/s), Inference-Zeit, Source (Agent + Modell + Backend)

### Dateizuordnung

| Datei | Modell | Bemerkung |
|---|---|---|
| Hund_vs._Katze_Vor-_und_Nachteile.html | GPT-OSS-120B Q8_0 | |
| Hund_oder_Katze_welcher_ist_besser.html | Qwen3-Next-80B-A3B Instruct Q4_K_M | Enthaelt TTS-Audio (5 OGG-Blobs, ~9 MB) |
| Hund_oder_Katze_Vergleich.html | Qwen3-Next-80B-A3B Thinking Q4_K_M | |
| Hund_oder_Katze_besserep_Hund_oder_Katze_besser.html | MiniMax-M2.5 Q2_K_XL | Besserer der 2 Runs (schneller, tiefere Debatte) |
| Hund_oder_Katze_Der_Vergleich.html | Qwen3-235B-A22B Instruct Q2_K_XL | |
| Hund_versus_Katze.html | GLM-4.7-REAP-218B-A32B IQ3_XXS | Negativ-Showcase |
