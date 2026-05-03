from typing import TypedDict, List, Annotated
import operator


class GraphState(TypedDict):
    raw_resume: str
    target_jd: str
    gap_list: List[str]
    refined_resume: str
    feedback: str
    revision_count: int
