import pytest
from pydantic import BaseModel

from src.tools.structured_generation.local_provider import LocalStructuredProvider


class Output(BaseModel):
    value: str


def test_local_provider_uses_the_same_validated_structured_contract():
    provider = LocalStructuredProvider(
        lambda **_: {"value": "local"}
    )

    result = provider.generate(
        system_prompt="system",
        user_prompt="user",
        output_model=Output,
        task_name="phase24-test",
    )

    assert provider.provider_name == "local"
    assert result == Output(value="local")


def test_local_provider_is_not_implicitly_available():
    with pytest.raises(RuntimeError, match="Phase 24 benchmark"):
        LocalStructuredProvider().generate(
            system_prompt="system",
            user_prompt="user",
            output_model=Output,
            task_name="phase24-test",
        )
