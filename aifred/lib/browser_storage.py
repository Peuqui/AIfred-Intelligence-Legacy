"""
Browser Storage Integration für AIfred

Handhabt Cookie-Lesen/Schreiben für Device-ID via rx.call_script().

Reflex hat keine native Cookie-Unterstützung, daher werden JavaScript-Snippets
generiert die via rx.call_script() ausgeführt werden.

Usage:
    # In State.on_load():
    yield rx.call_script(
        get_device_id_script(),
        callback=AIState.handle_device_id_loaded
    )

    # Im Callback wenn device_id == "NEW":
    return rx.call_script(set_device_id_script(new_id))
"""


# Cookie-Konfiguration
COOKIE_NAME = "aifred_device_id"
COOKIE_MAX_AGE_DAYS = 365


def get_device_id_script() -> str:
    """
    Generiert JavaScript zum Lesen der Device-ID aus Cookie.

    Das Skript gibt die Device-ID zurück oder "NEW" wenn kein Cookie existiert.
    Der Rückgabewert wird an den Callback übergeben.

    Returns:
        JavaScript-Code als String
    """
    return f"""
(function() {{
    const name = "{COOKIE_NAME}=";
    const cookies = document.cookie.split(';');
    for (let c of cookies) {{
        c = c.trim();
        if (c.indexOf(name) === 0) {{
            return c.substring(name.length);
        }}
    }}
    return "NEW";
}})()
"""


def set_device_id_script(device_id: str) -> str:
    """
    Generiert JavaScript zum Setzen der Device-ID als Cookie.

    Cookie-Attribute:
    - path=/: Gilt für gesamte Domain
    - max-age: 1 Jahr in Sekunden
    - SameSite=Lax: Verhindert CSRF, erlaubt aber normale Navigation

    Args:
        device_id: Die zu speichernde Device-ID (16 hex chars)

    Returns:
        JavaScript-Code als String
    """
    # Validierung: Nur alphanumerische Zeichen erlauben
    safe_id = "".join(c for c in device_id if c.isalnum())[:32]
    if not safe_id:
        raise ValueError("Invalid device_id for cookie")

    max_age_seconds = COOKIE_MAX_AGE_DAYS * 24 * 60 * 60

    return f'document.cookie = "{COOKIE_NAME}={safe_id}; path=/; max-age={max_age_seconds}; SameSite=Lax";'


def clear_device_id_script() -> str:
    """
    Generiert JavaScript zum Löschen des Device-ID Cookies.

    Setzt max-age=0 um Cookie sofort zu invalidieren.

    Returns:
        JavaScript-Code als String
    """
    return f'document.cookie = "{COOKIE_NAME}=; path=/; max-age=0";'
