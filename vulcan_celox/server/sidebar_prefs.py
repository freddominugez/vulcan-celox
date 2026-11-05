"""What Settings can hide from the sidebar."""

from __future__ import annotations

from typing import Any, Dict, List

from vulcan_celox.server.local_http import HttpError

# Settings itself stays, or there would be no way back
SIDEBAR_ITEMS = frozenset({
    "inicio", "overview", "node", "codigo", "terminals", "ambiente", "depuracao", "agentes", "prompts", "agentes-uso",
    "agentes-branches", "agentes-historico", "tasks", "notes", "tags", "index", "ajuda",
    "section-sessions", "section-sites", "section-node",
})


def valid_sidebar_hidden(value: Any) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item in SIDEBAR_ITEMS for item in value):
        raise HttpError(400, "sidebar_hidden deve ser uma lista de itens da barra lateral")
    return sorted(set(value))


def apply_sidebar_prefs(body: Dict[str, Any], prefs: Dict[str, Any]) -> bool:
    """Items hidden in Settings and the bar collapsed to icons. True if `prefs` changed and must be saved."""
    changed = False
    if "sidebar_hidden" in body:
        prefs["sidebar_hidden"] = valid_sidebar_hidden(body["sidebar_hidden"])
        changed = True
    if "sidebar_collapsed" in body:
        if not isinstance(body["sidebar_collapsed"], bool):
            raise HttpError(400, "sidebar_collapsed deve ser verdadeiro ou falso")
        prefs["sidebar_collapsed"] = body["sidebar_collapsed"]
        changed = True
    return changed


def sidebar_payload(prefs: Dict[str, Any]) -> Dict[str, Any]:
    """`sidebar_collapsed` is null while the user never chose: the interface then decides by the window width."""
    return {"sidebar_hidden": prefs.get("sidebar_hidden", []), "sidebar_collapsed": prefs.get("sidebar_collapsed")}
