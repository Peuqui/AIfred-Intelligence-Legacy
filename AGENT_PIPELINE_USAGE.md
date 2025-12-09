# Agent Pipeline Usage Guide

## Problem & Lösung

### Häufige Probleme bei Agent-Pipelines:
1. **Nur letzter Agent-Output sichtbar**: Agents geben ihre Outputs nicht weiter
2. **Keine Bezugnahme auf tatsächliche Änderungen**: Agents arbeiten isoliert ohne Kontext
3. **Tippfehler in Agent-Namen**: Agents werden nicht gefunden

### Lösung für effektive Agent-Pipelines:

#### 1. Sequenzielle Pipeline mit Datenweitergabe
```markdown
Pipeline: Agent1 → Agent2 → Agent3

WICHTIG:
- Output von Agent1 MUSS an Agent2 weitergegeben werden
- Jeder Agent soll seinen Report ausgeben
- Finale Konsolidierung aller Reports
```

#### 2. Parallele Ausführung (Alternative)
```markdown
1. Basis-Agent (z.B. diff-analyzer) liefert Kontext
2. Parallel: Multiple Agents nutzen den Kontext
3. Konsolidierung aller parallelen Reports
```

## Best Practices

### Für Code Reviews:
1. **Immer mit diff-analyzer starten**: Liefert strukturierte Änderungsliste
2. **Kontext weitergeben**: Nachfolgende Agents brauchen die Änderungsliste
3. **Alle Outputs zeigen**: Jeder Agent-Report ist wertvoll
4. **Finale Zusammenfassung**: Konsolidierte Sicht aller Findings

### Agent-Rollen im review-agents Command:
- **diff-analyzer**: Git diff Analyse, strukturierte Änderungsliste
- **primary-code-reviewer**: Security, Bugs, Performance Issues
- **context-analyzer**: Prüft ob Issues intentional sind
- **security-validator**: Zweitmeinung bei kritischen Issues

## Troubleshooting

### Wenn Agents nur allgemeine Vorschläge machen:
- Prüfen ob diff-analyzer korrekt läuft
- Sicherstellen dass diff-Output weitergegeben wird
- Agent-Namen auf Tippfehler prüfen

### Wenn nur ein Agent-Output erscheint:
- Command-Definition prüfen
- Explizit angeben: "Zeige alle Agent-Outputs"
- Sicherstellen dass Agents nicht überschrieben werden

## Beispiel-Command-Definition

```markdown
# review-agents.md
Code Review mit sequenzieller Agent-Pipeline:

1. **diff-analyzer**: Analysiert git diff
2. **primary-code-reviewer**: Prüft Änderungen
3. **context-analyzer**: Validiert Issues  
4. **security-validator**: Zweitmeinung

WICHTIG:
- Output weitergeben zwischen Agents
- Alle Reports anzeigen
- Finale Zusammenfassung erstellen
```