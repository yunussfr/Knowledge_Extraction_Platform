from pydantic import BaseModel

from src.tools.structured_generation.routing_provider import RoutingStructuredProvider


class Output(BaseModel):
    value: str


class Batch(BaseModel):
    records: list[dict] = []
    warnings: list[str] = []


class LocalUnavailable:
    provider_name = "fixture-local"

    def generate(self, **_):
        raise RuntimeError("local unavailable")


class CloudProvider:
    provider_name = "fixture-cloud"

    def generate(self, **_):
        return Output(value="cloud fallback")


def test_local_first_requires_benchmark_approval(monkeypatch):
    monkeypatch.setenv("LOCAL_FIRST_ENABLED", "true")
    monkeypatch.delenv("LOCAL_FIRST_BENCHMARK_APPROVED", raising=False)
    provider = RoutingStructuredProvider(local=LocalUnavailable(), cloud=CloudProvider())
    assert provider.provider_name == "fixture-cloud"
    assert provider.generate(system_prompt="", user_prompt="", output_model=Output, task_name="test").value == "cloud fallback"


def test_approved_local_first_escalates_to_cloud_on_local_failure(monkeypatch):
    monkeypatch.setenv("LOCAL_FIRST_ENABLED", "true")
    monkeypatch.setenv("LOCAL_FIRST_BENCHMARK_APPROVED", "true")
    provider = RoutingStructuredProvider(local=LocalUnavailable(), cloud=CloudProvider())
    assert provider.provider_name == "local-first"
    assert provider.generate(system_prompt="", user_prompt="", output_model=Output, task_name="test").value == "cloud fallback"


class LocalRejectedBatch:
    provider_name = "fixture-local"

    def generate(self, **_):
        return Batch(warnings=["record rejected"])


def test_approved_local_first_escalates_when_batch_is_silently_rejected(monkeypatch):
    monkeypatch.setenv("LOCAL_FIRST_ENABLED", "true")
    monkeypatch.setenv("LOCAL_FIRST_BENCHMARK_APPROVED", "true")
    provider = RoutingStructuredProvider(local=LocalRejectedBatch(), cloud=CloudProvider())
    assert provider.generate(system_prompt="", user_prompt="", output_model=Batch, task_name="test").value == "cloud fallback"


class BatchWithMissingEvidence(BaseModel):
    records: list[dict] = [{"data": {"name": "Alice"}, "field_evidence": {}}]
    warnings: list[str] = []


def test_approved_local_first_escalates_when_field_evidence_is_missing(monkeypatch):
    monkeypatch.setenv("LOCAL_FIRST_ENABLED", "true")
    monkeypatch.setenv("LOCAL_FIRST_BENCHMARK_APPROVED", "true")
    provider = RoutingStructuredProvider(local=LocalMissingEvidence(), cloud=CloudProvider())
    assert provider.generate(system_prompt="", user_prompt="Source URL: https://example.test\nChunk content:\nAlice", output_model=BatchWithMissingEvidence, task_name="test").value == "cloud fallback"


class LocalMissingEvidence:
    provider_name = "fixture-local"

    def generate(self, **_):
        return BatchWithMissingEvidence()
