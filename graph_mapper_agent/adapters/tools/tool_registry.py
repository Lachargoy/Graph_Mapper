from __future__ import annotations
#aither/adapters/tools/tool_registry.py
from dataclasses import dataclass, field
from typing import Any, Callable


ToolCallable = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class ToolRegistry:
    """
    Registro local de tools del carril Aither.

    Esta pieza sirve para el runner local del "servidor" de tools y
    evita acoplar el arranque del proceso a un solo nombre hardcodeado.
    """

    _tools: dict[str, ToolCallable] = field(default_factory=dict)

    def register(self, tool_name: str, tool_callable: ToolCallable) -> None:
        if not tool_name.strip():
            raise ValueError("ToolRegistry requiere `tool_name` no vacio.")
        self._tools[tool_name] = tool_callable

    def invoke(self, tool_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        try:
            tool = self._tools[tool_name]
        except KeyError as exc:
            raise KeyError(f"Tool no registrada: {tool_name}") from exc
        return tool(input_data)

    def list_tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))
