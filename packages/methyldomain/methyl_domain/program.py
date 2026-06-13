"""DomainProgram JSON IR — declarative high-level workflow language."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ForeachSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    collection: str
    item: str
    index: Optional[str] = None
    parallel: bool = False


class ActionStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str
    in_: Optional[Dict[str, str]] = Field(default=None, alias="in")
    out: Optional[Dict[str, str]] = None
    node_key: Optional[str] = None


class IfStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    if_: str = Field(alias="if")
    then: List["ProgramStep"] = Field(default_factory=list)
    else_: List["ProgramStep"] = Field(default_factory=list, alias="else")


class ForeachStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    foreach: ForeachSpec
    steps: List["ProgramStep"] = Field(default_factory=list)


ProgramStep = Union[ActionStep, IfStep, ForeachStep, Dict[str, Any]]


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
    phases: List[ProgramPhase] = Field(default_factory=list)


IfStep.model_rebuild()
