import logging
import os
import uuid
import json
import asyncio
import threading  # new import for thread safety
from typing import Dict, Literal, List
from langgraph.graph import END, START, StateGraph, MessagesState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv
import os
import concurrent.futures
import datetime  # ensure datetime is imported
import re
from tool import manage_role

load_dotenv()
# Set environment variables for LangChain tracing and your project details.
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_API_KEY"] = "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"
os.environ["LANGCHAIN_PROJECT"] = "pr-definite-forever-12"
os.environ["LANGCHAIN_MODEL"] = "gemini-1.5-pro"
user_stats = {}
role_hierarchy = []
# File where user stats are persisted.
USER_STATS_FILE = "user_stats.json"
CRITERIA_FILE = "criteria.json"
ROLE_HIERARCHY_FILE = "role_hierarchy.json"
DECISIONS_FILE = "decisions.json"  # file to store decisions

class DecisionEngine:
    def __init__(self):
        self.executor = concurrent.futures.ThreadPoolExecutor()
        self.user_stats = ""
        self.criteria = ""
        self.role_hierarchy = ""
        self.decisions_lock = threading.Lock()  # lock for thread-safe decisions update
        self._setup_environment()
        self.tools = [manage_role]
        self.tool_node = ToolNode(self.tools)
        self.model = ChatGoogleGenerativeAI(model="gemini-2.0-pro-exp", temperature=0.0).bind_tools(self.tools)
        self.memory = MemorySaver()
        self.workflow = self._initialize_workflow()

    def _setup_environment(self):
        self._load_user_stats()
        self._load_criteria()
        self._load_role_hierarchy()
        self._load_decisions()  # load previous decisions for context
  
    def _initialize_workflow(self):
        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", self.call_model)
        workflow.add_node("tool_node", self.tool_node)
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", self.should_continue)
        workflow.add_edge("tool_node", "agent")
        return workflow.compile()

    def _load_role_hierarchy(self):
        """Load the role_hierarchy from a JSON file if it exists."""
        global role_hierarchy
        try:
            with open(ROLE_HIERARCHY_FILE, "r") as f:
                role_hierarchy = json.load(f)
                print("done loading role hierarchy")
        except FileNotFoundError:
            role_hierarchy = []
        self.role_hierarchy = role_hierarchy

    def _load_user_stats(self):
        """Load the user_stats from a JSON file if it exists."""
        global user_stats
        try:
            with open(USER_STATS_FILE, "r") as f:
                user_stats = json.load(f)
                print("done loading user stats")
        except FileNotFoundError:
            user_stats = {}
            print("ℹ️ No existing user_stats.json found. Starting fresh.")
        self.user_stats = user_stats

    def _load_criteria(self):
        """Load the criteria list from the JSON file if it exists."""
        try:
            with open(CRITERIA_FILE, "r") as f:
                criteria_list = json.load(f)
                print("done loading criteria")
        except FileNotFoundError:
            criteria_list = []
        self.criteria = criteria_list

    def _load_decisions(self):
        """Load previous decisions from a JSON file for context."""
        try:
            with open(DECISIONS_FILE, "r") as f:
                self.decisions = json.load(f)
                print("done loading previous decisions")
        except FileNotFoundError:
            self.decisions = []
            print("ℹ️ No existing decisions.json found. Starting fresh for decisions.")

    def _save_decisions(self):
        """Persist the current decisions to a JSON file."""
        with open(DECISIONS_FILE, "w") as f:
            json.dump(self.decisions, f, indent=2)

    @staticmethod
    def should_continue(state: MessagesState) -> Literal["tool_node", END]:
        """
        If the last message includes a request for tool calls, go to 'tool_node'. 
        Otherwise, end the chain.
        """
        last_message = state["messages"][-1]
        return "tool_node" if last_message.tool_calls else END

    def run_agent(self):
        """
        Process each user in a simple for-loop (NO concurrency).
        """
        results = []
        
        for user_id, user_data in self.user_stats.items():
            # Build the initial state for each user
            state = MessagesState(messages=[HumanMessage(content=f"{user_data}")])
            cfg = {
                "thread_id": str(uuid.uuid4()),
                "checkpoint_ns": "decision_engine",
                "checkpoint_id": str(uuid.uuid4()),
            }
            
            # Invoke the workflow synchronously
            result = self.workflow.invoke(state, cfg)
            results.append(result)

        return results

    def call_model(self, state: MessagesState):
        """
        Call the model with the given state by evaluating Discord server role management.
        This version includes explicit instructions for:
          - Preventing Redundancy.
          - Better Role Hierarchy Management.
          - Safeguards Against Unauthorized Escalations.
          - Consideration of criteria priority.
          - Appropriate role assignment logic based on the user's current role.
        """
        messages = state["messages"]
        user_data = messages[0].content

        # Create a detailed string of criteria including their priority.
        criteria_details = "\n".join(
            f" • {c['original_message']} (priority: {c['priority']})"
            for c in self.criteria if c["enabled"]
        )
        
        role_hierarchy = self.role_hierarchy
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")

        EnhancedPrompt = f"""
You are a **Discord Server Management Assistant**, responsible for making precise role management decisions based on the provided data.

---

## **Guidelines for Decision Making**
1. **Data Completeness**: Take action **only** if complete user statistics are available. If data is partial or missing, **do not** perform irreversible actions.
2. **Criteria Interpretation**: Criteria reference **various time intervals** (from one day to one month) and have a **priority rating (1 to 10)**. Higher values indicate greater importance.
3. **Role Hierarchy Awareness**: The role hierarchy is **ordered from highest to lowest**. A role is **higher** if it appears **earlier** in the list.

---

## **Role Management Logic**
- `"assign_role"` → If the user has **no role** or only holds the **default role** (`@everyone`).
- `"upgrade_role"` → If the suggested role is **higher** than the user's current role.
  - If **no specific role** is mentioned, promote **only to the next immediate role** in the hierarchy.
- `"degrade_role"` → If the suggested role is **lower** than the user's current role.
  - If **no specific role** is mentioned, demote **only to the next immediate lower role** in the hierarchy.
- `"kick"` → If the user's behavior is **clearly unacceptable**.
- `"no_change"` → If no modifications are required, **document the reason**.

---

## **Data Processing Instructions**
- **Current Date:** {current_date}
- Analyze only **the current day's statistics**.
- **Date Format:** YYYY-MM-DD

---

## **Input Data**
### **User Data**
{user_data}

### **Criteria (multiple may apply)**
{criteria_details}

### **Role Hierarchy (from highest to lowest)**
{role_hierarchy}

---

## **Decision-Making Approach**
To ensure accurate role management, follow a structured **Chain of Thought** process:

1. **Assess Data Completeness**:
   - If data is **incomplete or ambiguous**, set `"human_intervention": true` and **do not** take action.
   - If data is **complete**, proceed to the next step.

2. **Evaluate Criteria**:
   - Independently analyze each criterion.
   - Identify the **highest-priority criterion** met by the user.
   - If multiple criteria apply, prioritize the action **with the highest assigned priority**.

3. **Determine Action Based on Hierarchy**:
   - Compare the **user's current role** with the **suggested role**.
   - Follow the **promotion/demotion rules**:
     - If **no specific target role** is given, move to **the next level up or down**.
     - If the **current role already exceeds** the suggested role, **do nothing**.

4. **Handle Special Cases**:
   - If the decision involves a **critical or irreversible** action (e.g., `"kick"`), set `"human_intervention": true`.

---
Tools attached:
- manage_role: If there is any change needed in the user's role, use this tool to manage a user's role in the server.If not then set the action to "no_change" and write the reason for not taking any action under 20 words.

"""

        if len(messages) == 1 and isinstance(messages[0], HumanMessage):
            messages = [
                SystemMessage(content=EnhancedPrompt),
                messages[0]
            ]
        response = self.model.invoke(messages)
        ai_content = response.content.strip() if response.content else ""

        # # Remove markdown code block formatting if present
        # markdown_pattern = r"^```(?:json)?\s*([\s\S]+?)\s*```$"
        # match = re.match(markdown_pattern, ai_content)
        # if match:
        #     ai_content = match.group(1).strip()

        # Update the state's messages with the AI's response.
        return {"messages": [response]}

        # Attempt to parse the decision output and store it.
        # try:
        #     decision_output = json.loads(ai_content)
        # except json.JSONDecodeError:
        #     print(f"Error parsing decision output: {ai_content}")
        #     decision_output = []
        
        # if isinstance(decision_output, list) and decision_output:
        #     with self.decisions_lock:
        #         self.decisions.extend(decision_output)
        #         self._save_decisions()

        

import logging

if __name__ == "__main__":
    # Configure the logging level and format
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    engine = DecisionEngine()
    (engine.run_agent())

    
                

