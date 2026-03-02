"""Streaming text span with O(1) DOM append via useEffect.

Instead of React doing ``textContent = fullString`` on every state delta
(O(n²) total DOM work over n updates), this component tracks the last
rendered length and only appends the NEW characters via ``el.append()``.

The ``text`` prop is bound to ``AIState.current_ai_response`` which grows
during streaming.  Each React render only appends the delta — O(1).

When the streaming box unmounts (``is_generating = False``), the span
is destroyed.  On next mount, a fresh empty span with ``lastLen = 0``
is created.
"""

from __future__ import annotations

from reflex.components.el.elements.inline import Span
from reflex.vars.base import Var


class StreamingText(Span):
    """A span that appends only new text via useEffect (O(1) per update)."""

    text: Var[str]

    @classmethod
    def create(cls, *children, **props):  # type: ignore[override]
        if "id" not in props:
            raise ValueError("StreamingText requires an explicit 'id' prop")
        return super().create(*children, **props)

    def _exclude_props(self) -> list[str]:
        """Exclude text from DOM attributes — it's only used in useEffect hooks."""
        return ["text"]

    def add_imports(self) -> dict:
        return {"react": ["useEffect", "useRef"]}

    def add_hooks(self) -> list[str | Var]:
        ref = self.get_ref()
        text_js = self.text._js_expr
        return [
            f"const lastLen_{ref} = useRef(0);",
            f"""
useEffect(() => {{
    const text = {text_js};
    const el = {ref}.current;
    if (!el) return;
    if (text.length > lastLen_{ref}.current) {{
        el.append(text.substring(lastLen_{ref}.current));
        lastLen_{ref}.current = text.length;
    }} else if (text.length === 0 && lastLen_{ref}.current > 0) {{
        el.textContent = '';
        lastLen_{ref}.current = 0;
    }}
}}, [{text_js}]);
""",
        ]


streaming_text = StreamingText.create
