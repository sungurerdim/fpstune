"""The UI's file types never depend on the machine's registry.

Windows' registry can map ".js" to text/plain (some editors and SDKs register
it so); Python's mimetypes reads that, the browser then refuses the module
script, and the packaged UI opens as a blank page.
"""

from __future__ import annotations

import mimetypes

import fpstune.api.main  # noqa: F401  (importing it pins the types)


def test_scripts_are_served_as_javascript_whatever_the_registry_says() -> None:
    mimetypes.add_type("text/plain", ".js")  # what a polluted registry injects
    import importlib

    importlib.reload(fpstune.api.main)

    assert mimetypes.guess_type("index-abc.js")[0] == "text/javascript"
    assert mimetypes.guess_type("index-abc.css")[0] == "text/css"
