from src.state import GraphState


def jd_analyzer_node(state: GraphState) -> GraphState:
    jd_text = state.get("target_jd", "")

    keywords = [
        kw.strip()
        for kw in jd_text.replace(",", " ").replace(";", " ").split()
        if len(kw.strip()) > 2
    ]

    state["gap_list"] = keywords
    state["revision_count"] = state.get("revision_count", 0)

    return state
