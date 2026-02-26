"""
Agent Configuration Module

Manages agent definitions (identity, prompts, toggles)
via a JSON configuration file at data/agents.json.

Each agent has:
- display_name, emoji, description, role
- prompts: mapping of prompt layer names to file paths (relative to prompts/{lang}/)
- toggles: default states for personality/reasoning/thinking

Sampling parameters (top_k, top_p, etc.) are NOT stored here —
they come from the llama-swap YAML config per model at runtime.
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Optional

from .config import DATA_DIR

AGENTS_FILE = DATA_DIR / "agents.json"

# Valid agent roles
VALID_ROLES = ("main", "critic", "judge", "vision", "custom")


@dataclass
class AgentConfig:
    """Configuration for a single agent."""

    display_name: str
    emoji: str
    description: str
    role: str  # "main" | "critic" | "judge" | "vision" | "custom"

    # Prompt file paths relative to prompts/{lang}/
    # Keys: "identity", "personality", "task", "reminder", + role-specific
    prompts: dict[str, str] = field(default_factory=dict)

    # Default toggle states
    toggles: dict[str, bool] = field(default_factory=lambda: {
        "personality": True,
        "reasoning": False,
        "thinking": True,
    })

    def to_dict(self) -> dict:
        return asdict(self)


def _default_agents() -> dict[str, dict]:
    """Return the 3 default agents as raw dicts."""
    return {
        "aifred": {
            "display_name": "AIfred",
            "emoji": "\U0001f3a9",
            "description": "Gentleman-Berater und KI-Butler",
            "role": "main",
            "prompts": {
                "identity": "aifred/identity.txt",
                "personality": "aifred/personality.txt",
                "reminder": "aifred/reminder.txt",
                "task": "aifred/system_minimal.txt",
                "direct": "aifred/direct.txt",
                "refinement": "aifred/refinement.txt",
                "defense": "aifred/defense.txt",
                "rag": "aifred/system_rag.txt",
            },
            "toggles": {
                "personality": True,
                "reasoning": False,
                "thinking": True,
            },
        },
        "sokrates": {
            "display_name": "Sokrates",
            "emoji": "\U0001f3db\ufe0f",
            "description": "Scharfsinniger Philosoph und Kritiker",
            "role": "critic",
            "prompts": {
                "identity": "sokrates/identity.txt",
                "personality": "sokrates/personality.txt",
                "reminder": "sokrates/reminder.txt",
                "task": "sokrates/system_minimal.txt",
                "direct": "sokrates/direct.txt",
                "critic": "sokrates/critic.txt",
                "tribunal": "sokrates/tribunal.txt",
            },
            "toggles": {
                "personality": True,
                "reasoning": False,
                "thinking": True,
            },
        },
        "salomo": {
            "display_name": "Salomo",
            "emoji": "\U0001f451",
            "description": "Weiser Richter und Synthesist",
            "role": "judge",
            "prompts": {
                "identity": "salomo/identity.txt",
                "personality": "salomo/personality.txt",
                "reminder": "salomo/reminder.txt",
                "task": "salomo/system_minimal.txt",
                "direct": "salomo/direct.txt",
                "mediator": "salomo/mediator.txt",
                "judge": "salomo/judge.txt",
            },
            "toggles": {
                "personality": True,
                "reasoning": False,
                "thinking": True,
            },
        },
        "vision": {
            "display_name": "Vision",
            "emoji": "\U0001f4f7",
            "description": "Vision Language Model fuer Bildanalyse",
            "role": "vision",
            "prompts": {
                "identity": "vision/identity.txt",
                "personality": "aifred/personality.txt",
                "task": "vision/vision_ocr.txt",
                "task_qa": "vision/vision_qa.txt",
            },
            "toggles": {
                "personality": True,
                "reasoning": False,
                "thinking": True,
            },
        },
    }


def _dict_to_config(data: dict) -> AgentConfig:
    """Convert a raw dict to an AgentConfig instance."""
    return AgentConfig(
        display_name=data["display_name"],
        emoji=data["emoji"],
        description=data["description"],
        role=data["role"],
        prompts=data.get("prompts", {}),
        toggles=data.get("toggles", {}),
    )


def load_agents() -> dict[str, AgentConfig]:
    """Load agent configurations from data/agents.json.

    If the file doesn't exist, creates it with default agents.
    """
    if not AGENTS_FILE.exists():
        save_agents_raw(_default_agents())

    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        raw: dict = json.load(f)

    agents_data = raw.get("agents", raw)
    return {
        agent_id: _dict_to_config(agent_data)
        for agent_id, agent_data in agents_data.items()
    }


def load_agents_raw() -> dict[str, dict]:
    """Load agent configurations as raw dicts (for UI serialization)."""
    if not AGENTS_FILE.exists():
        save_agents_raw(_default_agents())

    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        raw: dict = json.load(f)

    agents_data: dict[str, dict] = raw.get("agents", raw)
    return agents_data


def save_agents_raw(agents: dict[str, dict]) -> None:
    """Save agent configurations from raw dicts."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(AGENTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"agents": agents}, f, indent=2, ensure_ascii=False)


def save_agents(agents: dict[str, AgentConfig]) -> None:
    """Save agent configurations to data/agents.json."""
    raw = {agent_id: config.to_dict() for agent_id, config in agents.items()}
    save_agents_raw(raw)


def get_agent_ids() -> list[str]:
    """Return list of configured agent IDs."""
    agents = load_agents_raw()
    return list(agents.keys())


def get_agent_config(agent_id: str) -> Optional[AgentConfig]:
    """Get config for a specific agent, or None if not found."""
    agents = load_agents()
    return agents.get(agent_id)


def create_agent(
    agent_id: str,
    display_name: str,
    emoji: str,
    description: str,
    role: str = "custom",
) -> AgentConfig:
    """Create a new agent and save to config.

    Also creates prompt template files for the agent.

    Args:
        agent_id: Unique identifier (lowercase, no spaces)
        display_name: Human-readable name
        emoji: Agent emoji character
        description: Short description
        role: Agent role ("main", "critic", "judge", "custom")

    Returns:
        The newly created AgentConfig

    Raises:
        ValueError: If agent_id already exists or role is invalid
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {VALID_ROLES}")

    agents = load_agents_raw()
    if agent_id in agents:
        raise ValueError(f"Agent '{agent_id}' already exists")

    # Build prompt paths for the new agent
    prompts = {
        "identity": f"{agent_id}/identity.txt",
        "personality": f"{agent_id}/personality.txt",
        "task": f"{agent_id}/system_minimal.txt",
        "direct": f"{agent_id}/direct.txt",
    }

    # Add role-specific prompts
    if role == "critic":
        prompts["critic"] = f"{agent_id}/critic.txt"
    elif role == "judge":
        prompts["mediator"] = f"{agent_id}/mediator.txt"
        prompts["judge"] = f"{agent_id}/judge.txt"

    config = AgentConfig(
        display_name=display_name,
        emoji=emoji,
        description=description,
        role=role,
        prompts=prompts,
    )

    # Create prompt template files
    _create_prompt_files(agent_id, display_name, role)

    # Save to config
    agents[agent_id] = config.to_dict()
    save_agents_raw(agents)

    return config


def delete_agent(agent_id: str) -> None:
    """Delete an agent from config.

    Does NOT delete prompt files (user might want to keep them).

    Raises:
        ValueError: If agent is a default agent or doesn't exist
    """
    if agent_id in ("aifred", "sokrates", "salomo", "vision"):
        raise ValueError(f"Cannot delete default agent '{agent_id}'")

    agents = load_agents_raw()
    if agent_id not in agents:
        raise ValueError(f"Agent '{agent_id}' not found")

    del agents[agent_id]
    save_agents_raw(agents)


def update_agent(agent_id: str, updates: dict) -> AgentConfig:
    """Update an agent's configuration.

    Args:
        agent_id: Agent to update
        updates: Dict with fields to update (shallow merge)

    Returns:
        Updated AgentConfig

    Raises:
        ValueError: If agent doesn't exist
    """
    agents = load_agents_raw()
    if agent_id not in agents:
        raise ValueError(f"Agent '{agent_id}' not found")

    agents[agent_id].update(updates)
    save_agents_raw(agents)

    return _dict_to_config(agents[agent_id])


def _create_prompt_files(agent_id: str, display_name: str, role: str) -> None:
    """Create template prompt files for a new agent in both languages."""
    from .config import PROJECT_ROOT

    prompts_dir = PROJECT_ROOT / "prompts"

    # Role-specific templates
    role_templates = _get_role_templates(display_name, role)

    for lang in ("de", "en"):
        agent_dir = prompts_dir / lang / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        templates = role_templates.get(lang, role_templates.get("de", {}))

        for filename, content in templates.items():
            filepath = agent_dir / filename
            if not filepath.exists():
                filepath.write_text(content, encoding="utf-8")


def _get_role_templates(display_name: str, role: str) -> dict[str, dict[str, str]]:
    """Get prompt templates for a given role.

    Returns:
        Dict mapping lang -> {filename: content}
    """
    templates: dict[str, dict[str, str]] = {
        "de": {
            "identity.txt": f"Du bist {display_name}.",
            "personality.txt": "",
            "system_minimal.txt": (
                "Beantworte die Frage des Benutzers praezise und hilfreich.\n"
                "Heute ist {current_weekday}, der {current_date}, {current_time} Uhr.\n"
                "Das aktuelle Jahr ist {current_year}."
            ),
            "direct.txt": (
                "Beantworte die Frage des Benutzers direkt und hilfreich.\n"
                "Heute ist {current_weekday}, der {current_date}, {current_time} Uhr."
            ),
        },
        "en": {
            "identity.txt": f"You are {display_name}.",
            "personality.txt": "",
            "system_minimal.txt": (
                "Answer the user's question precisely and helpfully.\n"
                "Today is {current_weekday}, {current_date}, {current_time}.\n"
                "The current year is {current_year}."
            ),
            "direct.txt": (
                "Answer the user's question directly and helpfully.\n"
                "Today is {current_weekday}, {current_date}, {current_time}."
            ),
        },
    }

    # Add role-specific templates
    if role == "critic":
        templates["de"]["critic.txt"] = (
            "Analysiere die Antwort kritisch. Finde Schwaechen, Luecken "
            "und moegliche Verbesserungen. Runde {round_num}."
        )
        templates["en"]["critic.txt"] = (
            "Critically analyze the response. Find weaknesses, gaps "
            "and possible improvements. Round {round_num}."
        )
    elif role == "judge":
        templates["de"]["mediator.txt"] = (
            "Synthetisiere die verschiedenen Perspektiven zu einem "
            "ausgewogenen Urteil. Runde {round_num}."
        )
        templates["de"]["judge.txt"] = (
            "Fasse die Debatte zusammen und sprich ein abschliessendes Urteil."
        )
        templates["en"]["mediator.txt"] = (
            "Synthesize the different perspectives into a balanced "
            "judgment. Round {round_num}."
        )
        templates["en"]["judge.txt"] = (
            "Summarize the debate and deliver a final verdict."
        )

    return templates
