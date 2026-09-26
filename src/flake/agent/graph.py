"""StateGraph: load_context -> agent -> gate -> tools -> ... -> record -- owned by Lane A."""


def run_plan(group_id: str, brief: str) -> dict:
    raise NotImplementedError("Lane A: run one plan through the graph, return the resulting episode")
