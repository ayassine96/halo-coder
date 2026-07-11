#!/usr/bin/env python3
"""TDAD — Test Impact Analysis FastAPI service (TDAD-R1..R6).

POST /analyze — accepts repo + changed_files + spec_id, returns affected tests.
GET  /health  — index loaded, service ready.
GET  /metrics — Prometheus metrics.
"""

import os

from fastapi import FastAPI
from pydantic import BaseModel

from halo.tdad.graph_store import GraphStore
from halo.tdad.ast_builder import build_graph, analyze_changed_files
from halo.tdad.incremental import incremental_update, full_reindex


app = FastAPI(title="HALO TDAD", version="2.0.0-halo")

_graph = None
_repo_path = os.environ.get("HALO_TDAD_REPO", "")
_index_path = os.environ.get("HALO_TDAD_INDEX", "/tmp/halo-tdad-graph.json")


class AnalyzeRequest(BaseModel):
    repo: str
    changed_files: list = []
    spec_id: str = ""


class AnalyzeResponse(BaseModel):
    affected_tests: list = []
    confidence: float = 0.0
    uncovered_paths: list = []


class IndexRequest(BaseModel):
    repo: str
    changed_files: list = []


@app.get("/health")
async def health():
    return {"status": "ok", "indexed": _graph is not None}


@app.get("/metrics")
async def metrics():
    if _graph is None:
        modules = 0
        tests = 0
        edges = 0
    else:
        modules = _graph.module_count
        tests = _graph.test_count
        edges = _graph.edge_count
    lines = [
        "# HELP halo_tdad_modules Total indexed modules",
        "# TYPE halo_tdad_modules gauge",
        f"halo_tdad_modules {modules}",
        "# HELP halo_tdad_tests Total indexed test files",
        "# TYPE halo_tdad_tests gauge",
        f"halo_tdad_tests {tests}",
        "# HELP halo_tdad_edges Total code→test edges",
        "# TYPE halo_tdad_edges gauge",
        f"halo_tdad_edges {edges}",
    ]
    return "\n".join(lines) + "\n"


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """Analyze a repo and return affected tests for changed files (TDAD-R3)."""
    global _graph, _repo_path
    if _graph is None or (req.repo and req.repo != _repo_path):
        _repo_path = req.repo
        _graph = GraphStore(_index_path)
        if os.path.isdir(req.repo):
            _graph.load()
            if _graph.module_count == 0:
                build_graph(req.repo, _graph)
                _graph.save()
    if req.changed_files and _graph is not None:
        incremental_update(req.repo, req.changed_files, _graph)
        _graph.save()

    affected, confidence, uncovered = analyze_changed_files(req.repo, req.changed_files, _graph)

    return AnalyzeResponse(
        affected_tests=affected,
        confidence=round(confidence, 2),
        uncovered_paths=uncovered,
    )


@app.post("/index")
async def index_repo(req: IndexRequest):
    """Index or re-index a repository."""
    global _graph, _repo_path
    _repo_path = req.repo
    _graph = GraphStore(_index_path)
    if req.changed_files:
        incremental_update(req.repo, req.changed_files, _graph)
    else:
        full_reindex(req.repo, _graph)
    _graph.save()
    return {
        "modules": _graph.module_count,
        "tests": _graph.test_count,
        "edges": _graph.edge_count,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("HALO_TDAD_PORT", "8402")))