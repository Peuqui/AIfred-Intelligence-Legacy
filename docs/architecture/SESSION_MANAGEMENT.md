# Session Persistence System

**Version:** 2.7+
**Status:** Production
**Module:** `aifred/lib/session_storage.py`

---

## Overview

AIfred Intelligence implements a cookie-based session persistence system that allows chat history to survive browser restarts, tab closures, and mobile app backgrounding. Each device receives a unique identifier stored in a browser cookie, enabling automatic session restoration across visits.

**Key Features:**
- Cookie-based device identification (128-bit secure tokens)
- Server-side session storage (JSON files)
- Automatic save after each message
- Mobile-friendly (survives iOS/Android app suspension)
- Privacy-focused (device-local, no cloud sync)

---

## Architecture

### System Flow

```
Browser/Device
    ↓
┌─────────────────────────────────────────────┐
│ Cookie: aifred_device_id                    │
│ Value: <32 hex chars> (128-bit entropy)     │
│ Persistent, HttpOnly, SameSite=Lax          │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Client connects to AIfred                   │
│ - Device ID sent in Cookie header           │
│ - Reflex State receives device_id           │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Session Restoration Check                   │
│ - Validate device_id format (security)      │
│ - Load session file if exists               │
│ - Restore chat_history to State             │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ User interacts with chat                    │
│ - Sends messages                            │
│ - Receives AI responses                     │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Auto-Save after each message                │
│ - chat_history serialized to JSON           │
│ - Saved to ~/.config/aifred/sessions/       │
│ - File: <device_id>.json                    │
└─────────────────────────────────────────────┘
```

### File Structure

```
~/.config/aifred/
└── sessions/
    ├── a1b2c3d4e5f6...7890.json   # Device 1 (desktop)
    ├── f9e8d7c6b5a4...3210.json   # Device 2 (mobile)
    └── ...
```

**Session File Format:**
```json
{
  "device_id": "a1b2c3d4e5f67890...",
  "created": "2025-12-20T14:30:00",
  "last_seen": "2025-12-26T17:15:00",
  "data": {
    "chat_history": [
      {
        "role": "user",
        "content": "Hello AIfred"
      },
      {
        "role": "assistant",
        "content": "Hello! How can I help you today?"
      }
    ]
  }
}
```

---

## Implementation Details

### Device ID Generation

**Security:**
- 128-bit entropy (32 hex characters)
- Generated with `secrets.token_hex(16)` (cryptographically secure)
- Format: `^[a-f0-9]{32}$` (lowercase hex only)

**Example:**
```python
device_id = "a1b2c3d4e5f67890abcdef1234567890"
```

**Validation:**
```python
def _sanitize_device_id(device_id: str) -> str:
    """
    Strict format validation prevents path traversal attacks.

    Allowed: Only lowercase hex (a-f0-9), exactly 32 chars
    Rejected: "..", "/", uppercase, special chars, wrong length
    """
    if not re.match(r'^[a-f0-9]{32}$', device_id):
        raise ValueError("Invalid device_id format")
    return device_id
```

### Cookie Configuration

**Set by:** Server-side (Reflex backend)
**Cookie Properties:**
```python
{
    "name": "aifred_device_id",
    "value": "<32 hex chars>",
    "max_age": 365 * 24 * 60 * 60,  # 1 year
    "http_only": True,               # Not accessible via JavaScript
    "same_site": "lax",              # CSRF protection
    "secure": False                  # True if HTTPS enabled
}
```

**Browser Storage:**
- Persistent (survives browser restart)
- Domain-specific (one per AIfred instance)
- Automatically sent with every request

### Session Initialization Flow

**On page load:**
```python
def on_load_session(self, device_id: str = ""):
    """
    Called by Reflex on component mount.
    Receives device_id from cookie (or empty if new device).
    """
    # Guard against multiple calls
    if self._session_initialized:
        return
    self._session_initialized = True

    # Validate format
    is_valid_id = device_id and re.match(r'^[a-f0-9]{32}$', device_id)

    if not is_valid_id:
        # New device - generate ID and set cookie
        new_id = generate_device_id()
        self.device_id = new_id
        set_device_id_cookie(new_id)  # JavaScript injection
        return

    # Known device - load session
    self.device_id = device_id
    session = load_session(device_id)

    if session and session.get("data"):
        self._restore_session(session)
        self.session_restored = True
```

### Auto-Save Mechanism

**Trigger:** After every chat message (user or assistant)

```python
def _save_current_session(self):
    """
    Auto-save current chat_history to session file.
    Called after each message exchange.
    """
    if not self.device_id:
        return  # Session not initialized

    from .lib.session_storage import save_session

    session_data = {
        "chat_history": self.chat_history
        # Future: add more state (settings, preferences)
    }

    save_session(self.device_id, session_data)
```

**Save Function:**
```python
def save_session(device_id: str, data: Dict[str, Any]) -> bool:
    """
    Save session data to JSON file.

    Thread-safe: Uses atomic write (write to temp, then rename).
    Error-handling: Returns False on failure, doesn't crash.
    """
    try:
        _ensure_session_dir()
        path = get_session_path(device_id)

        session = {
            "device_id": device_id,
            "created": existing.get("created", now),
            "last_seen": now,
            "data": data
        }

        # Atomic write
        temp_path = path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(session, f, indent=2, ensure_ascii=False)
        temp_path.replace(path)  # Atomic rename

        return True
    except Exception as e:
        print(f"Session save error: {e}")
        return False
```

---

## Security Considerations

### Path Traversal Protection

**Attack Vector:**
```
device_id = "../../../etc/passwd"  # Malicious input
```

**Prevention:**
1. Strict format validation (only `[a-f0-9]{32}`)
2. Regex check rejects `.`, `/`, and all non-hex chars
3. Path resolution check ensures result is within `SESSION_DIR`

```python
def get_session_path(device_id: str) -> Path:
    safe_id = _sanitize_device_id(device_id)  # Raises on invalid
    path = (SESSION_DIR / f"{safe_id}.json").resolve()

    # Ensure within SESSION_DIR
    try:
        path.relative_to(SESSION_DIR.resolve())
    except ValueError:
        raise ValueError("Path traversal attempt detected")

    return path
```

### Cookie Security

**HttpOnly:** Prevents JavaScript access (XSS mitigation)
**SameSite=Lax:** Prevents CSRF attacks
**Secure Flag:** Should be enabled if using HTTPS (currently optional)

**Recommendation for production:**
```python
cookie_config = {
    "http_only": True,
    "same_site": "strict",  # Even stricter than "lax"
    "secure": True          # Require HTTPS
}
```

### Privacy

**Data Storage:**
- Stored locally on server (`~/.config/aifred/sessions/`)
- No cloud sync, no external transmission
- Each device has independent session

**Identification:**
- Device ID is random, not linked to user identity
- No IP logging, no user tracking
- Session files can be manually deleted

---

## Mobile Considerations

### iOS Safari
**Challenge:** iOS aggressively suspends background tabs
**Solution:** Cookie-based persistence survives suspension
- Session restored when tab reactivated
- No data loss even after hours in background

### Android Chrome
**Challenge:** Tab eviction under memory pressure
**Solution:** Cookie persists across tab recreation
- Chat history restored on new tab load
- Seamless continuation of conversation

### PWA Mode
**Progressive Web Apps:**
- Cookie works identically in PWA mode
- Full session persistence
- Recommended for mobile users

---

## Usage Patterns

### First-Time User
```
1. User opens AIfred
2. No cookie present
3. Server generates new device_id
4. Cookie set in browser
5. Empty chat (no history)
6. User sends first message
7. Session auto-saved
```

### Returning User
```
1. User opens AIfred
2. Cookie sent with request
3. Server loads session file
4. chat_history restored to State
5. User sees previous conversation
6. UI indicates: "✅ Session loaded: <device_id> (N messages)"
```

### Multi-Device User
```
Desktop:
- device_id: a1b2c3...
- Session file: a1b2c3....json
- Chat history: Desktop conversations

Mobile:
- device_id: f9e8d7...
- Session file: f9e8d7....json
- Chat history: Mobile conversations

Note: Sessions are independent (no sync)
```

### Session Cleared by User
```
1. User clears browser cookies
2. device_id cookie deleted
3. Next visit: Treated as new device
4. New device_id generated
5. Old session file remains but is orphaned
```

---

## Debug Output

**Session Events:**
```
✅ Session loaded: a1b2c3d4... (15 messages)
🆕 New device: f9e8d7c6... (setting cookie)
💾 Session auto-saved (23 messages)
⚠️ Session load failed: Invalid device_id format
```

**Log Location:**
- `logs/aifred_debug.log`
- Console output (development mode)

---

## Configuration

### Session Directory

**Default:**
```python
SESSION_DIR = Path.home() / ".config" / "aifred" / "sessions"
```

**Override via environment:**
```bash
export AIFRED_SESSION_DIR="/custom/path/sessions"
```

### Session Expiry

**Current:** Sessions never expire automatically

**Future Enhancement:**
```python
# Planned feature
SESSION_MAX_AGE = 30 * 24 * 60 * 60  # 30 days
SESSION_CLEANUP_INTERVAL = 24 * 60 * 60  # Daily cleanup
```

---

## API Reference

### `session_storage.py`

#### `generate_device_id() -> str`
Generate cryptographically secure 128-bit device ID.

**Returns:** 32-character hex string

**Example:**
```python
device_id = generate_device_id()
# "a1b2c3d4e5f67890abcdef1234567890"
```

#### `load_session(device_id: str) -> Optional[Dict[str, Any]]`
Load session data for device.

**Args:**
- `device_id`: 32-char hex string

**Returns:** Session dict or None if not found

**Raises:** `ValueError` on invalid device_id

**Example:**
```python
session = load_session("a1b2c3d4...")
if session:
    chat_history = session["data"]["chat_history"]
```

#### `save_session(device_id: str, data: Dict[str, Any]) -> bool`
Save session data for device.

**Args:**
- `device_id`: 32-char hex string
- `data`: Session data dict (must be JSON-serializable)

**Returns:** True on success, False on error

**Example:**
```python
data = {"chat_history": [...]}
success = save_session("a1b2c3d4...", data)
```

#### `delete_session(device_id: str) -> bool`
Delete session file for device.

**Args:**
- `device_id`: 32-char hex string

**Returns:** True if deleted, False if not found or error

**Example:**
```python
deleted = delete_session("a1b2c3d4...")
```

#### `list_sessions() -> List[Tuple[str, Dict[str, Any]]]`
List all sessions with metadata.

**Returns:** List of (device_id, session_data) tuples

**Example:**
```python
for device_id, session in list_sessions():
    msg_count = len(session["data"]["chat_history"])
    print(f"{device_id}: {msg_count} messages")
```

---

## Troubleshooting

### Session not loading

**Check:**
1. Cookie present? (Browser dev tools → Application → Cookies)
2. Session file exists? (`ls ~/.config/aifred/sessions/`)
3. Valid device_id format? (32 hex chars)
4. File permissions? (readable by AIfred user)

**Debug:**
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Session corruption

**Symptoms:**
- JSON parse errors
- Missing chat_history
- Incomplete messages

**Fix:**
```bash
# Backup session
cp ~/.config/aifred/sessions/<device_id>.json ~/backup.json

# Delete corrupted session
rm ~/.config/aifred/sessions/<device_id>.json

# Clear cookie and restart
# (New session will be created)
```

### Multiple devices same history

**Not supported by design:**
- Each device has independent session
- No multi-device sync

**Workaround:**
```bash
# Manual sync (copy session file)
scp device1:~/.config/aifred/sessions/<id>.json \
    device2:~/.config/aifred/sessions/<id>.json
```

---

## Future Enhancements

**Planned:**
- [ ] Session expiry and cleanup (auto-delete old sessions)
- [ ] Export session to file (JSON/Markdown)
- [ ] Import session from file
- [ ] Session merge (combine multiple devices)
- [ ] Encrypted session storage (optional)
- [ ] Cloud sync (opt-in, E2EE)
- [ ] Session branching (fork conversation history)

**Under Consideration:**
- [ ] Multi-user support (login-based sessions)
- [ ] Session sharing (export with anonymization)
- [ ] Session search (find messages across all sessions)
- [ ] Session analytics (usage statistics)

---

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture
- [CACHE_SYSTEM.md](CACHE_SYSTEM.md) - History compression
- [MULTI_AGENT_SYSTEM.md](MULTI_AGENT_SYSTEM.md) - Multi-agent persistence
- [../SETTINGS_FORMAT.md](../SETTINGS_FORMAT.md) - Settings vs Session data

---

## Changelog

**v2.7.0** (Nov 2025)
- Initial session persistence implementation
- Cookie-based device identification
- Auto-save after each message

**v2.7.1** (Nov 2025)
- Added path traversal protection
- Improved error handling
- Mobile-friendly session restoration

---

**Last Updated:** 2025-12-26
**Maintainer:** AIfred Intelligence Team
