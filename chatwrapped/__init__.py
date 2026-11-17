"""ChatWrapped — Spotify Wrapped for your AI chats.

Reads official data exports (ChatGPT, Claude, Gemini) 100% locally and
produces a terminal summary, a self-contained HTML "Wrapped" story with a
downloadable share card, and a JSON stats file.

ChatWrapped never makes a network call.
"""

__version__ = "0.1.0"

PRIVACY_NOTE = (
    "Privacy: everything was parsed locally on this machine. "
    "ChatWrapped makes zero network calls — nothing left your device."
)

__all__ = ["__version__", "PRIVACY_NOTE"]
