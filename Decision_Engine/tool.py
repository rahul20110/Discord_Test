# tools.py

import logging
import os
import json
import threading
from typing import Dict, List, Literal, TypedDict, Annotated
from langgraph.graph import END, START, StateGraph, MessagesState
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# The JSON file your bot reads from in its background task
ROLE_REQUESTS_FILE = "role_requests.json"

# A lock to ensure file access is thread-safe (if multiple calls happen at once).
file_lock = threading.Lock()
@tool
def manage_role(
    user_id: str,
    action: str,
    role: str,
    reason: str,
    human_intervention: bool = False
) -> str:
    """
    Manage a user's role in the server.
    Args:
        user_id(str): The ID of the user to manage.
        action(str): The action to take. It can be "assign_role", "upgrade_role", "degrade_role", "kick", "no_change".
        role(str): The role to assign.
        reason(str): The reason for the action.
        human_intervention(Optional[bool]): Whether to intervention of human is required or not.
    Returns:
        str: A message indicating the action taken.
    """
    logger.info("manage_role called with user_id=%s, action=%s, role=%s, reason=%s",
                user_id, action, role, reason)

    if action == "no_change":
        message = f"No action taken for user {user_id} (no_change)."
        logger.info(message)
        return message

    # Build a request entry
    request_entry = {
        "user_id": user_id,
        "action": action,
        "role": role,
        "reason": reason,
        "human_intervention": human_intervention
    }

    # Append it to role_requests.json
    with file_lock:
        try:
            with open(ROLE_REQUESTS_FILE, "r") as f:
                existing_requests = json.load(f)
        except FileNotFoundError:
            existing_requests = []

        existing_requests.append(request_entry)

        with open(ROLE_REQUESTS_FILE, "w") as f:
            json.dump(existing_requests, f, indent=2)

    message = (
        f"Role for user {user_id} has been set to {role}."
    )
    logger.info(message)
    return message
