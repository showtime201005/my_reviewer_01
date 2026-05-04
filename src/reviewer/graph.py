"""LangGraph graph assembly for the Reviewer subgraph."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from reviewer.llm import create_default_llm
from reviewer.nodes import (
    CompletenessNode,
    InformationRecallNode,
    LogicalCoherenceNode,
    PresentationSpecificityNode,
    QuestionAlignmentNode,
    SourceQualityNode,
    aggregator_node,
    input_validator_node,
)
from reviewer.state import ReviewerState


def build_reviewer_graph(llm=None):
    """Build and compile the reviewer LangGraph.

    Args:
        llm: Optional LLM instance (ChatOpenAI-compatible).
             Defaults to create_default_llm() if not provided.

    Returns:
        A compiled LangGraph ready to invoke.
    """
    if llm is None:
        llm = create_default_llm()

    # Instantiate dimension reviewer nodes
    qa = QuestionAlignmentNode(llm)
    ir = InformationRecallNode(llm)
    cp = CompletenessNode(llm)
    lc = LogicalCoherenceNode(llm)
    sq = SourceQualityNode(llm)
    ps = PresentationSpecificityNode(llm)

    # Build the graph
    graph = StateGraph(ReviewerState)

    graph.add_node("input_validator", input_validator_node)
    graph.add_node("qa_reviewer", qa)
    graph.add_node("ir_reviewer", ir)
    graph.add_node("cp_reviewer", cp)
    graph.add_node("lc_reviewer", lc)
    graph.add_node("sq_reviewer", sq)
    graph.add_node("ps_reviewer", ps)
    graph.add_node("aggregator", aggregator_node)

    # Fan-out / fan-in: validate → [6 reviewers in parallel] → aggregate
    reviewer_nodes = [
        "qa_reviewer", "ir_reviewer", "cp_reviewer",
        "lc_reviewer", "sq_reviewer", "ps_reviewer",
    ]

    graph.add_edge(START, "input_validator")
    for node_name in reviewer_nodes:
        graph.add_edge("input_validator", node_name)
        graph.add_edge(node_name, "aggregator")
    graph.add_edge("aggregator", END)

    return graph.compile()
