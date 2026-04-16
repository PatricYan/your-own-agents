"""Tests for the web API server."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace with a test agent."""
    from agentpipe.storage.definitions import DefinitionStore

    store = DefinitionStore(tmp_path)
    store.save_model(
        "test-model",
        {
            "name": "test-model",
            "provider": "http",
            "connection": {"base_url": "http://localhost:9999"},
            "status": "active",
        },
    )
    store.save_agent(
        "test-agent",
        {
            "name": "test-agent",
            "pipeline": {
                "name": "test-pipeline",
                "execution_strategy": "fail_fast",
                "tasks": [
                    {"name": "a", "goal": "Do A", "primary_model": "test-model"},
                    {
                        "name": "b",
                        "goal": "Do B",
                        "primary_model": "test-model",
                        "depends_on": ["a"],
                    },
                ],
            },
            "model_configs": ["test-model"],
        },
    )
    return tmp_path


@pytest.fixture
def client(workspace):
    from agentpipe.web.api import create_app

    app = create_app(workspace=str(workspace))
    return TestClient(app)


class TestListEndpoints:
    def test_list_pipelines(self, client):
        resp = client.get("/api/pipelines")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["name"] == "test-agent"

    def test_get_pipeline(self, client):
        resp = client.get("/api/pipelines/test-agent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-pipeline"
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["levels"] == [["a"], ["b"]]

    def test_get_pipeline_not_found(self, client):
        resp = client.get("/api/pipelines/nonexistent")
        assert resp.status_code == 404

    def test_list_runs_empty(self, client):
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        assert resp.json()["runs"] == []

    def test_list_models(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200
        assert len(resp.json()["models"]) == 1

    def test_get_pipeline_node_structure(self, client):
        """Verify node data includes permissions, depends_on, etc."""
        resp = client.get("/api/pipelines/test-agent")
        nodes = resp.json()["nodes"]
        node_b = next(n for n in nodes if n["id"] == "b")
        assert node_b["goal"] == "Do B"
        assert node_b["model"] == "test-model"
        assert "*" in node_b["permissions"]  # default permissions use "*" key
        assert node_b["depends_on"] == ["a"]
