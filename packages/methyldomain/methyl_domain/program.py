"""DomainProgram JSON IR — declarative high-level workflow language."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class CollectionInSpec(BaseModel):
    """Reference to a scope collection or project-bound path."""

    model_config = ConfigDict(extra="ignore")

    ref: Optional[str] = None
    var: Optional[str] = None


class ForeachSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    collection: Optional[str] = None
    in_: Optional[Union[str, CollectionInSpec]] = Field(default=None, alias="in")
    item: Optional[str] = None
    as_: Optional[str] = Field(default=None, alias="as")
    index: Optional[str] = None
    parallel: bool = False

    def resolved_item(self) -> str:
        return self.as_ or self.item or "item"

    def resolved_collection_var(self) -> str:
        if self.collection:
            return self.collection
        if isinstance(self.in_, CollectionInSpec):
            if self.in_.var:
                return self.in_.var
            if self.in_.ref and self.in_.ref.startswith("project."):
                return self.in_.ref.split(".", 1)[1]
            if self.in_.ref:
                return self.in_.ref.split(".")[-1]
        if isinstance(self.in_, str):
            if self.in_.startswith("project."):
                return self.in_.split(".", 1)[1]
            return self.in_
        raise ValueError("foreach requires collection or in")


class ActionStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Optional[str] = None
    do: Optional[str] = None
    in_: Optional[Dict[str, Any]] = Field(default=None, alias="in")
    with_: Optional[Dict[str, Any]] = Field(default=None, alias="with")
    out: Optional[Dict[str, str]] = None
    node_key: Optional[str] = None

    def action_name(self) -> str:
        name = self.do or self.action
        if not name:
            raise ValueError("action step requires do or action")
        return name


class IfStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    if_: str = Field(alias="if")
    then: List["ProgramStep"] = Field(default_factory=list)
    else_: List["ProgramStep"] = Field(default_factory=list, alias="else")


class ForeachStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    foreach: Optional[ForeachSpec] = None
    for_: Optional[ForeachSpec] = Field(default=None, alias="for")
    steps: List["ProgramStep"] = Field(default_factory=list)
    do: List["ProgramStep"] = Field(default_factory=list)

    def spec(self) -> ForeachSpec:
        s = self.for_ or self.foreach
        if s is None:
            raise ValueError("foreach step missing for/foreach spec")
        return s

    def body(self) -> List[Any]:
        return self.do if self.do else self.steps


class ParallelStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    parallel: List["ProgramStep"] = Field(default_factory=list)


ProgramStep = Union[ActionStep, IfStep, ForeachStep, ParallelStep, Dict[str, Any]]


class ProgramPhase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    foreach: Optional[ForeachSpec] = None
    steps: List[Any] = Field(default_factory=list)


class DomainProgram(BaseModel):
    """Client-side program lowered to WorkflowDefinitionSpec + context_json."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    programVersion: int = 1
    name: str
    description: Optional[str] = None
    projectPath: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    declarations: Dict[str, Any] = Field(default_factory=dict)
    phases: List[ProgramPhase] = Field(default_factory=list)
    body: List[Any] = Field(default_factory=list)


IfStep.model_rebuild()
ForeachStep.model_rebuild()
ParallelStep.model_rebuild()
