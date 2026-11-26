import os
import sys


def app_dir() -> str:
    """Folder holding bundled resources (data/, drivers/)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "HLineStation")
    os.makedirs(d, exist_ok=True)
    return d


def snapshot_dir() -> str:
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(docs):
        docs = os.path.expanduser("~")
    d = os.path.join(docs, "HLineStation Snapshots")
    os.makedirs(d, exist_ok=True)
    return d
