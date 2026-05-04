"""Example: embedding the reviewer as a subgraph in a parent LangGraph."""

from dotenv import load_dotenv
load_dotenv()

from reviewer import build_reviewer_graph
from reviewer.state import create_initial_state

# Build the reviewer graph (can pass custom LLM)
reviewer_graph = build_reviewer_graph()

# Prepare input state
state = create_initial_state(
    task="比較 Apple 與 Samsung 2024 年的智慧手機策略",
    report=open("examples/sample_report.md", encoding="utf-8").read(),
)

# Invoke directly
final_state = reviewer_graph.invoke(state)
output = final_state["final_output"]

print(output.human_readable_text)

# To embed in a parent graph:
#
# from langgraph.graph import StateGraph, START, END
#
# parent_graph = StateGraph(ParentState)
# parent_graph.add_node("reviewer", reviewer_graph)
# parent_graph.add_edge(START, "reviewer")
# parent_graph.add_edge("reviewer", END)
# app = parent_graph.compile()
