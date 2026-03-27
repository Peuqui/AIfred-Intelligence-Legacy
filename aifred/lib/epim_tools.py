"""EPIM database tools for LLM function calling.

Provides 4 tools for full CRUD on EPIM entities:
- epim_search: Search/read tasks, contacts, notes, todos, passwords
- epim_create: Create new entries
- epim_update: Update existing entries
- epim_delete: Soft-delete entries
"""

import json
import logging
from typing import Any, Optional

from .function_calling import Tool

logger = logging.getLogger(__name__)


def _serialize(obj: Any) -> Any:
    """JSON-serialize EPIM results (handle datetime etc.)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return "<binary>"
    return obj


def get_epim_tools(lang: str = "de") -> list[Tool]:
    """Create EPIM database tools for LLM function calling.

    Returns empty list if EPIM is not available.
    """
    from .epim_db import get_epim_db

    db = get_epim_db()
    if db is None:
        return []

    # ----------------------------------------------------------
    # epim_search
    # ----------------------------------------------------------
    async def _epim_search(
        entity_type: str,
        query: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        completed: Optional[bool] = None,
        limit: int = 20,
    ) -> str:
        """Search EPIM database."""
        from .logging_utils import log_message
        log_message(f"🗓️ epim_search: {entity_type} query={query}")

        entity = entity_type.lower()
        results: list[dict] | dict | None = None

        if entity in ("task", "tasks", "termin", "termine", "kalender", "calendar"):
            results = db.search_tasks(
                title=query, date_from=date_from, date_to=date_to, limit=limit,
            )
        elif entity in ("contact", "contacts", "kontakt", "kontakte"):
            results = db.search_contacts(name=query, limit=limit)
        elif entity in ("note", "notes", "notiz", "notizen"):
            results = db.search_notes(title=query, text=query, limit=limit)
        elif entity in ("todo", "todos", "aufgabe", "aufgaben"):
            results = db.search_todos(title=query, completed=completed, limit=limit)
        elif entity in ("password", "passwords", "passwort", "passwoerter"):
            results = db.search_passwords(subject=query, limit=limit)
        elif entity in ("category", "categories", "kategorie", "kategorien"):
            results = db.get_categories()
        elif entity in ("calendar_list", "kalender_liste"):
            results = db.get_calendars()
        elif entity in ("todolist", "todolists", "todoliste", "todolisten"):
            results = db.get_todolists()
        elif entity in ("notetree", "notetrees", "notizbaum"):
            results = db.get_notetrees()
        else:
            return json.dumps({"error": f"Unknown entity_type: {entity_type}. "
                              "Use: tasks, contacts, notes, todos, passwords, "
                              "categories, calendar_list, todolists, notetrees"})

        serialized = _serialize(results)
        count = len(serialized) if isinstance(serialized, list) else 1
        log_message(f"✅ epim_search: {count} {entity_type} gefunden")
        return json.dumps(serialized, ensure_ascii=False, default=str)

    # ----------------------------------------------------------
    # epim_create
    # ----------------------------------------------------------
    async def _epim_create(entity_type: str, data: dict) -> str:
        """Create a new EPIM entry."""
        from .logging_utils import log_message
        log_message(f"🗓️ epim_create: {entity_type}")

        entity = entity_type.lower()

        if entity in ("task", "termin", "kalender"):
            title = data.get("title", "Neuer Termin")
            new_id = db.create_task(
                title=title,
                start=data.get("start", ""),
                end=data.get("end", ""),
                location=data.get("location"),
                allday=data.get("allday", False),
                text=data.get("text"),
                priority=data.get("priority", 0),
                tags=data.get("tags"),
                calendar_id=data.get("calendar_id"),
                calendar_name=data.get("calendar_name") or data.get("calendar"),
                category_id=data.get("category_id"),
                category_name=data.get("category_name") or data.get("category"),
            )
            log_message(f"✅ epim_create: Task {new_id} '{title}'")
            return json.dumps({"success": True, "id": new_id, "title": title})

        elif entity in ("contact", "kontakt"):
            name = data.get("name", "Neuer Kontakt")
            new_id = db.create_contact(
                name=name,
                fields=data.get("fields"),
                tags=data.get("tags"),
            )
            log_message(f"✅ epim_create: Contact {new_id} '{name}'")
            return json.dumps({"success": True, "id": new_id, "name": name})

        elif entity in ("note", "notiz"):
            title = data.get("title", "Neue Notiz")
            new_id = db.create_note(
                title=title,
                tab_name=data.get("tab_name", "Tab 1"),
                tab_text=data.get("text", ""),
                tags=data.get("tags"),
                tree_id=data.get("tree_id"),
                tree_name=data.get("tree_name") or data.get("tree"),
            )
            log_message(f"✅ epim_create: Note {new_id} '{title}'")
            return json.dumps({"success": True, "id": new_id, "title": title})

        elif entity in ("todo", "aufgabe"):
            title = data.get("title", "Neue Aufgabe")
            new_id = db.create_todo(
                title=title,
                start=data.get("start"),
                end=data.get("end"),
                priority=data.get("priority", 0),
                text=data.get("text"),
                tags=data.get("tags"),
                list_id=data.get("list_id"),
                list_name=data.get("list_name") or data.get("list"),
            )
            log_message(f"✅ epim_create: Todo {new_id} '{title}'")
            return json.dumps({"success": True, "id": new_id, "title": title})

        elif entity in ("password", "passwort"):
            subject = data.get("subject", "Neuer Eintrag")
            new_id = db.create_password(
                subject=subject,
                fields=data.get("fields"),
                group_id=data.get("group_id"),
                tags=data.get("tags"),
            )
            log_message(f"✅ epim_create: Password {new_id} '{subject}'")
            return json.dumps({"success": True, "id": new_id, "subject": subject})

        return json.dumps({"error": f"Unknown entity_type: {entity_type}"})

    # ----------------------------------------------------------
    # epim_update
    # ----------------------------------------------------------
    async def _epim_update(entity_type: str, entity_id: int, data: dict) -> str:
        """Update an existing EPIM entry."""
        from .logging_utils import log_message
        log_message(f"🗓️ epim_update: {entity_type} id={entity_id}")

        entity = entity_type.lower()

        if entity in ("task", "termin"):
            ok = db.update_task(entity_id, **data)
        elif entity in ("contact", "kontakt"):
            ok = db.update_contact(
                entity_id,
                name=data.get("name"),
                fields=data.get("fields"),
                tags=data.get("tags"),
            )
        elif entity in ("note", "notiz"):
            ok = db.update_note(entity_id, title=data.get("title"), tags=data.get("tags"))
        elif entity in ("note_tab", "notiz_tab"):
            ok = db.update_note_tab(entity_id, name=data.get("name"), text=data.get("text"))
        elif entity in ("todo", "aufgabe"):
            ok = db.update_todo(entity_id, **data)
        elif entity in ("password", "passwort"):
            ok = db.update_password(
                entity_id,
                subject=data.get("subject"),
                fields=data.get("fields"),
                tags=data.get("tags"),
            )
        else:
            return json.dumps({"error": f"Unknown entity_type: {entity_type}"})

        status = "updated" if ok else "not found or unchanged"
        log_message(f"{'✅' if ok else '❌'} epim_update: {entity_type} {entity_id} → {status}")
        return json.dumps({"success": ok, "id": entity_id, "status": status})

    # ----------------------------------------------------------
    # epim_delete
    # ----------------------------------------------------------
    async def _epim_delete(entity_type: str, entity_id: int) -> str:
        """Soft-delete an EPIM entry."""
        from .logging_utils import log_message
        log_message(f"🗓️ epim_delete: {entity_type} id={entity_id}")

        entity = entity_type.lower()

        if entity in ("task", "termin"):
            ok = db.delete_task(entity_id)
        elif entity in ("contact", "kontakt"):
            ok = db.delete_contact(entity_id)
        elif entity in ("note", "notiz"):
            ok = db.delete_note(entity_id)
        elif entity in ("todo", "aufgabe"):
            ok = db.delete_todo(entity_id)
        elif entity in ("password", "passwort"):
            ok = db.delete_password(entity_id)
        else:
            return json.dumps({"error": f"Unknown entity_type: {entity_type}"})

        status = "deleted" if ok else "not found"
        log_message(f"{'✅' if ok else '❌'} epim_delete: {entity_type} {entity_id} → {status}")
        return json.dumps({"success": ok, "id": entity_id, "status": status})

    # ----------------------------------------------------------
    # Tool definitions
    # ----------------------------------------------------------
    search_desc = (
        "Durchsuche die EPIM-Datenbank (Kalender, Kontakte, Notizen, Todos, Passwörter). "
        "Verwende entity_type um den Bereich auszuwählen."
    ) if lang == "de" else (
        "Search the EPIM database (calendar, contacts, notes, todos, passwords). "
        "Use entity_type to select the area."
    )

    create_desc = (
        "Erstelle einen neuen Eintrag in der EPIM-Datenbank."
    ) if lang == "de" else (
        "Create a new entry in the EPIM database."
    )

    update_desc = (
        "Aktualisiere einen bestehenden EPIM-Eintrag."
    ) if lang == "de" else (
        "Update an existing EPIM entry."
    )

    delete_desc = (
        "Lösche einen EPIM-Eintrag (Soft-Delete, kann rückgängig gemacht werden)."
    ) if lang == "de" else (
        "Delete an EPIM entry (soft-delete, can be undone)."
    )

    return [
        Tool(
            name="epim_search",
            description=search_desc,
            parameters={
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Entity type: tasks, contacts, notes, todos, passwords, categories, calendar_list, todolists, notetrees",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search text (title, name, subject)",
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Start date filter (YYYY-MM-DD), only for tasks",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "End date filter (YYYY-MM-DD), only for tasks",
                    },
                    "completed": {
                        "type": "boolean",
                        "description": "Filter by completion status, only for todos",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 20)",
                    },
                },
                "required": ["entity_type"],
            },
            executor=_epim_search,
        ),
        Tool(
            name="epim_create",
            description=create_desc,
            parameters={
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Entity type: task, contact, note, todo, password",
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Entity data. Task: {title, start, end, location, allday, text, priority, tags}. "
                            "Contact: {name, fields: {Vorname, Nachname, Telefon, E-Mail, ...}, tags}. "
                            "Note: {title, text, tab_name, tree_id, tags}. "
                            "Todo: {title, start, end, priority, text, tags, list_id}. "
                            "Password: {subject, fields: {key: value, ...}, tags, group_id}."
                        ),
                    },
                },
                "required": ["entity_type", "data"],
            },
            executor=_epim_create,
        ),
        Tool(
            name="epim_update",
            description=update_desc,
            parameters={
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Entity type: task, contact, note, note_tab, todo, password",
                    },
                    "entity_id": {
                        "type": "integer",
                        "description": "ID of the entity to update",
                    },
                    "data": {
                        "type": "object",
                        "description": "Fields to update (same structure as create)",
                    },
                },
                "required": ["entity_type", "entity_id", "data"],
            },
            executor=_epim_update,
        ),
        Tool(
            name="epim_delete",
            description=delete_desc,
            parameters={
                "type": "object",
                "properties": {
                    "entity_type": {
                        "type": "string",
                        "description": "Entity type: task, contact, note, todo, password",
                    },
                    "entity_id": {
                        "type": "integer",
                        "description": "ID of the entity to delete",
                    },
                },
                "required": ["entity_type", "entity_id"],
            },
            executor=_epim_delete,
        ),
    ]
