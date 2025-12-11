# Login-/Registrierungssystem für AIfred-Intelligence

**Status**: Geplant (on ice - aufgeschoben)
**Erstellt**: 2025-12-10
**Aufwand**: ~14 neue Dateien, ~5 modifizierte Dateien

---

## Übersicht

**Ziel**: Multi-User Authentifizierung mit manueller Account-Erstellung durch Admin.

**Anforderungen**:
- Wenige bekannte Benutzer (Admin legt Accounts an)
- Benutzername + Passwort
- Login + Device-ID kombiniert (ein User kann mehrere Geräte mit je eigener Chat-History haben)
- Komplette Sperrung ohne Login (Redirect zur Login-Seite)

---

## Architektur

### Neue Dateistruktur

```
aifred/
├── lib/
│   ├── auth/                          # NEU: Auth-Paket
│   │   ├── __init__.py                # Exports
│   │   ├── models.py                  # Dataclasses: User, AuthSession
│   │   ├── password_utils.py          # Hashing, Validierung
│   │   ├── user_store.py              # User-CRUD (SQLite)
│   │   ├── session_manager.py         # Auth-Sessions (Login-Tokens)
│   │   ├── auth_service.py            # Zentrale Auth-Logik
│   │   └── rate_limiter.py            # Login-Versuch-Limitierung
│   │
│   ├── session_storage.py             # ERWEITERT: +user_id Feld
│   └── browser_storage.py             # ERWEITERT: +auth_token Cookie
│
├── components/                         # NEU: UI-Komponenten
│   ├── __init__.py
│   └── auth/
│       ├── __init__.py
│       ├── login_form.py              # Login-Formular
│       └── user_management.py         # Admin-Panel
│
├── pages/                              # NEU: Separate Seiten
│   ├── __init__.py
│   └── login.py                       # Login-Seite
│
├── state.py                           # ERWEITERT: +Auth-State
└── aifred.py                          # ERWEITERT: +Routing
```

---

## Implementierungsschritte

### Phase 1: Auth-Bibliothek (Backend)

#### 1.1 `aifred/lib/auth/models.py`
```python
@dataclass
class User:
    id: str                    # UUID
    username: str              # Eindeutig
    password_hash: str         # bcrypt
    display_name: str
    role: str                  # "user" | "admin"
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]
    failed_login_attempts: int
    locked_until: Optional[datetime]

@dataclass
class AuthSession:
    token: str                 # secrets.token_urlsafe(32)
    user_id: str
    device_id: str
    created_at: datetime
    expires_at: datetime       # +30 Tage
    is_valid: bool
```

#### 1.2 `aifred/lib/auth/password_utils.py`
- `hash_password(password) -> str` (bcrypt, 12 rounds)
- `verify_password(password, hash) -> bool`
- `check_password_strength(password) -> PasswordStrength`
- `generate_temporary_password() -> str`

#### 1.3 `aifred/lib/auth/user_store.py`
SQLite-Datenbank in `~/.config/aifred/aifred.db`

Funktionen:
- `init_database()` - Schema erstellen
- `create_user(username, password, display_name, role) -> User`
- `get_user_by_id(user_id) -> User`
- `get_user_by_username(username) -> User`
- `get_all_users() -> List[User]`
- `update_user(user_id, **kwargs) -> bool`
- `change_password(user_id, new_password) -> bool`
- `delete_user(user_id) -> bool`

#### 1.4 `aifred/lib/auth/session_manager.py`
- `create_auth_session(user_id, device_id) -> AuthSession`
- `validate_auth_token(token) -> Tuple[bool, user_id, device_id]`
- `invalidate_session(token) -> bool`
- `invalidate_all_user_sessions(user_id) -> int`
- `cleanup_expired_sessions() -> int`

#### 1.5 `aifred/lib/auth/auth_service.py`
Zentrale Logik:
- `authenticate(username, password, device_id) -> LoginResult`
- `get_auth_context(auth_token, device_id) -> AuthContext`
- `logout(auth_token) -> bool`
- `link_device_to_user(user_id, device_id) -> bool`

#### 1.6 `aifred/lib/auth/rate_limiter.py`
Memory-basiert:
- `check_rate_limit(identifier) -> Tuple[is_blocked, wait_seconds]`
- `record_failed_attempt(identifier)`
- `clear_failed_attempts(identifier)`

Config: 5 Versuche/Minute, 5 Min Sperre

#### 1.7 `aifred/lib/auth/__init__.py`
Exports aller wichtigen Funktionen und Klassen.

---

### Phase 2: Existierende Module erweitern

#### 2.1 `aifred/lib/browser_storage.py` erweitern
Neue Funktionen:
```python
AUTH_TOKEN_COOKIE = "aifred_auth_token"

def get_auth_token_script() -> str
def set_auth_token_script(token: str) -> str
def clear_auth_token_script() -> str
```

#### 2.2 `aifred/lib/session_storage.py` erweitern
- `save_session()`: Optionaler `user_id` Parameter
- Neue Funktion: `get_sessions_for_user(user_id) -> List[Dict]`

---

### Phase 3: UI-Komponenten

#### 3.1 `aifred/components/auth/login_form.py`
- Benutzername-Input
- Passwort-Input
- Login-Button mit Loading-State
- Fehlermeldungs-Anzeige

#### 3.2 `aifred/components/auth/user_management.py`
Admin-Panel mit:
- User-Tabelle (Username, Name, Rolle, Status, Letzter Login)
- "Neuer Benutzer" Modal
- Aktivieren/Deaktivieren Button
- Löschen Button

#### 3.3 `aifred/pages/login.py`
Standalone Login-Seite mit zentriertem Formular.

---

### Phase 4: State-Integration

#### 4.1 `aifred/state.py` erweitern

Neue State-Variablen:
```python
# Auth State
is_authenticated: bool = False
current_user_id: str = ""
current_username: str = ""
current_user_display_name: str = ""
current_user_role: str = ""
auth_token: str = ""

# Login Form
login_username: str = ""
login_password: str = ""
login_error: str = ""
login_loading: bool = False
```

Neue Event-Handler:
- `handle_auth_token_loaded(token)` - Callback nach Cookie-Read
- `do_login()` - Login durchführen
- `do_logout()` - Logout durchführen

`on_load()` erweitern:
1. Auth-DB initialisieren (einmalig)
2. Default-Admin erstellen falls keine User existieren
3. Auth-Token aus Cookie lesen
4. Bei gültigem Token: User laden
5. Bei ungültigem/fehlendem Token: Redirect zu /login

---

### Phase 5: Routing

#### 5.1 `aifred/aifred.py` erweitern

```python
@rx.page(route="/login", title="AIfred - Login")
def login_route() -> rx.Component:
    return login_page()

@rx.page(route="/", on_load=AIState.on_load)
def index() -> rx.Component:
    return rx.cond(
        AIState.is_authenticated,
        # Existierende UI
        ...,
        # Loading/Redirect Placeholder
        rx.center(rx.spinner(), height="100vh")
    )

@rx.page(route="/admin", on_load=AIState.on_load)
def admin_route() -> rx.Component:
    return rx.cond(
        AIState.is_authenticated & (AIState.current_user_role == "admin"),
        user_management_panel(),
        rx.redirect("/")
    )
```

---

### Phase 6: CLI-Tool für Admin-Erstellung

#### 6.1 `scripts/create_user.py`
```bash
python scripts/create_user.py --username admin --password geheim --role admin
```

---

## Datenbank-Schema (SQLite)

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role TEXT DEFAULT 'user',
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login TEXT,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TEXT
);

CREATE TABLE auth_sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    device_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_valid INTEGER DEFAULT 1
);

CREATE TABLE user_devices (
    user_id TEXT NOT NULL REFERENCES users(id),
    device_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (user_id, device_id)
);
```

---

## Sicherheit

| Aspekt | Implementierung |
|--------|-----------------|
| Passwort-Hashing | bcrypt, 12 rounds |
| Session-Tokens | `secrets.token_urlsafe(32)` (256 bit) |
| Cookie-Schutz | `SameSite=Strict` |
| Rate-Limiting | 5 Versuche/Min, dann 5 Min Sperre |
| Account-Lockout | Nach 5 Fehlversuchen 15 Min gesperrt |
| Session-Expiry | 30 Tage |

---

## Abhängigkeiten

```
# requirements.txt (NEU)
bcrypt>=4.0.0
```

---

## Kritische Dateien

**Neue Dateien:**
1. `aifred/lib/auth/__init__.py`
2. `aifred/lib/auth/models.py`
3. `aifred/lib/auth/password_utils.py`
4. `aifred/lib/auth/user_store.py`
5. `aifred/lib/auth/session_manager.py`
6. `aifred/lib/auth/auth_service.py`
7. `aifred/lib/auth/rate_limiter.py`
8. `aifred/components/__init__.py`
9. `aifred/components/auth/__init__.py`
10. `aifred/components/auth/login_form.py`
11. `aifred/components/auth/user_management.py`
12. `aifred/pages/__init__.py`
13. `aifred/pages/login.py`
14. `scripts/create_user.py`

**Zu modifizierende Dateien:**
1. `aifred/state.py` - Auth-State + Handler
2. `aifred/aifred.py` - Routing + Auth-Check
3. `aifred/lib/browser_storage.py` - Auth-Token Cookie
4. `aifred/lib/session_storage.py` - user_id Feld
5. `requirements.txt` - bcrypt

---

## Migration

Existierende Device-Sessions bleiben erhalten. Nach Login wird die Device-ID mit dem User verknüpft. Chat-History bleibt pro Gerät bestehen.

---

## Admin-Workflow

1. **Erstmalig**: Server startet → Default-Admin wird erstellt (Passwort muss geändert werden)
2. **Oder via CLI**: `python scripts/create_user.py --username admin --password xxx --role admin`
3. **Web-UI**: Admin meldet sich an → /admin → "Neuer Benutzer" → Formular ausfüllen
