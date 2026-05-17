from typing import TypedDict, List, Annotated
import operator


class GraphState(TypedDict):
    raw_resume: str
    target_jd: str
    gap_list: List[str]
    rich_context_list: List[str]
    rag_context: str
    refined_resume: str
    feedback: str
    revision_count: int


class AgentState(TypedDict):
    resume: str
    jd: str
    rag_context: str
    revised_resume: str
    internal_monologue: str
    tool_outputs: Annotated[list, operator.add]
