"""Provider-neutral semantic structured-generation contract."""

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel


OutputModel = TypeVar("OutputModel", bound=BaseModel)


@runtime_checkable
class StructuredGenerationProvider(Protocol):
    provider_name: str

    def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_model: type[OutputModel],
        task_name: str,
    ) -> OutputModel:
        ...
