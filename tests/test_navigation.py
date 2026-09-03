"""Every page must be reachable from somewhere in the app.

The automatic Streamlit sidebar is switched off
(``.streamlit/config.toml``: ``showSidebarNavigation = false``), so a page
exists for the user only if some other page links to it. Four pages shipped
without a link and were invisible in the running app despite being complete:
Payroll Recording, Inventory, Invoices, and Bills. Nothing failed, nothing
warned, the pages simply were not there.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "pages"

# Files a user can actually navigate from. Tests link to pages too, and a
# test's link reaches nobody.
SOURCES = [ROOT / "app.py"] + sorted(PAGES.glob("*.py")) + sorted((ROOT / "utils").glob("*.py"))


def test_the_sidebar_is_the_only_navigation_there_is():
    """If this ever flips back on, the reachability test below stops mattering."""
    config = (ROOT / ".streamlit" / "config.toml").read_text()
    assert "showSidebarNavigation = false" in config


def test_every_page_is_linked_from_the_app():
    linked = set()
    for source in SOURCES:
        text = source.read_text()
        linked.update(re.findall(r"[\"']pages/([\w.]+\.py)[\"']", text))

    orphans = sorted(
        page.name for page in PAGES.glob("*.py") if page.name not in linked
    )
    assert orphans == [], (
        "unreachable in the UI, no page links to them: " + ", ".join(orphans)
    )
