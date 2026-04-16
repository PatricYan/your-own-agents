"""Unit tests for agentpipe.storage — definitions and history stores."""

from agentpipe.storage.definitions import DefinitionStore
from agentpipe.storage.history import HistoryStore


class TestDefinitionStore:
    def test_agent_crud(self, tmp_path):
        store = DefinitionStore(tmp_path)
        store.save_agent("test", {"name": "test", "pipeline": {}})
        assert "test" in store.list_agents()
        data = store.load_agent("test")
        assert data["name"] == "test"
        store.delete_agent("test")
        assert "test" not in store.list_agents()

    def test_model_crud(self, tmp_path):
        store = DefinitionStore(tmp_path)
        store.save_model("gpt4", {"name": "gpt4", "provider": "openai"})
        assert "gpt4" in store.list_models()
        store.delete_model("gpt4")
        assert "gpt4" not in store.list_models()

    def test_task_crud(self, tmp_path):
        store = DefinitionStore(tmp_path)
        store.save_task("my_task", {"name": "my_task", "goal": "do stuff"})
        assert "my_task" in store.list_tasks()
        data = store.load_task("my_task")
        assert data["goal"] == "do stuff"


class TestHistoryStore:
    def test_save_and_get_run(self, tmp_path):
        store = HistoryStore(tmp_path)
        store.save_run({"id": "run-1", "pipeline_name": "test", "status": "completed"})
        run = store.get_run("run-1")
        assert run is not None
        assert run["status"] == "completed"

    def test_list_runs(self, tmp_path):
        store = HistoryStore(tmp_path)
        store.save_run({"id": "r1", "pipeline_name": "p", "status": "completed"})
        store.save_run({"id": "r2", "pipeline_name": "p", "status": "failed"})
        runs = store.list_runs()
        assert len(runs) == 2

    def test_get_missing_run(self, tmp_path):
        store = HistoryStore(tmp_path)
        assert store.get_run("nonexistent") is None
