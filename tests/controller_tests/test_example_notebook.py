"""Run the example workflow notebook the way a user would, on the mock driver.

The notebook is the front door of part 3, so every cell must keep working.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "3_build_your_workflow"
    / "example_workflow.ipynb"
)


def test_every_cell_of_the_notebook_runs(monkeypatch, capsys):
    # Jupyter runs a notebook from its own folder, so its relative paths start there.
    monkeypatch.chdir(NOTEBOOK.parent)
    namespace: dict = {}
    for cell in json.loads(NOTEBOOK.read_text())["cells"]:
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            exec(compile(source, str(NOTEBOOK), "exec"), namespace)
    printed = capsys.readouterr().out
    assert [line.split()[0] for line in printed.splitlines()] == ["True"] * 3, printed
