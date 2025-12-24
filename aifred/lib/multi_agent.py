"""
Multi-Agent Debate Orchestrator
AIfred (Main) + Sokrates (Critic)

Implements multi-agent debate patterns for improved answer quality:
- User-as-Judge: AIfred answers, Sokrates critiques, user decides
- Auto-Consensus: Iterative refinement until LGTM or max rounds
- Devil's Advocate: Pro and Contra arguments for balanced analysis
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any
from .llm_client import LLMClient
from .prompt_loader import (
    get_sokrates_critic_prompt,
    get_sokrates_devils_advocate_prompt,
    get_sokrates_refinement_prompt
)
from ..backends.base import LLMMessage, LLMOptions, LLMResponse


@dataclass
class DebateResult:
    """Result of a multi-agent debate session"""
    alfred_answer: str  # AIfred's final answer
    sokrates_critique: str = ""  # Sokrates' critique (user_judge, auto_consensus)
    sokrates_pro: str = ""  # Pro arguments (devils_advocate)
    sokrates_contra: str = ""  # Contra arguments (devils_advocate)
    rounds_used: int = 1  # Number of iterations (auto_consensus)
    consensus_reached: bool = True  # LGTM achieved?
    debate_history: List[Dict[str, str]] = field(default_factory=list)  # Full debate log


@dataclass
class DebateContext:
    """Context for an active debate session"""
    query: str
    history: List[Dict[str, str]]  # Conversation history
    llm_client: LLMClient
    model: str
    options: LLMOptions
    max_rounds: int = 3
    get_user_interjection: Optional[Callable[[], str]] = None  # Callback for user input


class MultiAgentOrchestrator:
    """Orchestrates AIfred + Sokrates debate patterns

    Prompts are loaded from external files:
    - prompts/de/sokrates/critic.txt
    - prompts/de/sokrates/devils_advocate.txt
    - prompts/de/sokrates/refinement.txt
    (and English versions in prompts/en/sokrates/)
    """

    def __init__(self):
        """Initialize the orchestrator"""
        pass

    def _get_critic_prompt(self) -> str:
        """Load Sokrates Critic prompt from external file"""
        return get_sokrates_critic_prompt()

    def _get_devils_advocate_prompt(self) -> str:
        """Load Sokrates Devil's Advocate prompt from external file"""
        return get_sokrates_devils_advocate_prompt()

    def _get_refinement_prompt(self, critique: str, user_interjection: str = "") -> str:
        """Load AIfred Refinement prompt from external file"""
        return get_sokrates_refinement_prompt(critique, user_interjection)

    async def user_as_judge(
        self,
        ctx: DebateContext,
        add_debug: Optional[Callable[[str], None]] = None
    ) -> DebateResult:
        """
        Pattern A: User-as-Judge

        1. AIfred answers the question
        2. Sokrates critiques the answer
        3. User decides (accept/improve)

        Returns result with alfred_answer and sokrates_critique
        """
        if add_debug:
            add_debug("🤝 Multi-Agent: User-as-Judge Modus")

        # Step 1: AIfred answers
        alfred_messages = self._build_messages(ctx.history, ctx.query)
        alfred_response = await ctx.llm_client.chat(ctx.model, alfred_messages, ctx.options)
        alfred_answer = alfred_response.text

        if add_debug:
            add_debug(f"🎩 AIfred: {len(alfred_answer)} Zeichen generiert")

        # Step 2: Sokrates critiques
        sokrates_messages = [
            {"role": "system", "content": self._get_critic_prompt()},
            {"role": "user", "content": f"Frage des Users: {ctx.query}"},
            {"role": "assistant", "content": f"AIfred's Antwort:\n{alfred_answer}"},
            {"role": "user", "content": "Analysiere diese Antwort kritisch."}
        ]
        sokrates_response = await ctx.llm_client.chat(ctx.model, sokrates_messages, ctx.options)
        sokrates_critique = sokrates_response.text

        if add_debug:
            add_debug(f"🧠 Sokrates: {len(sokrates_critique)} Zeichen Kritik")

        return DebateResult(
            alfred_answer=alfred_answer,
            sokrates_critique=sokrates_critique,
            rounds_used=1,
            consensus_reached="LGTM" in sokrates_critique.upper(),
            debate_history=[
                {"role": "alfred", "content": alfred_answer},
                {"role": "sokrates", "content": sokrates_critique}
            ]
        )

    async def auto_consensus(
        self,
        ctx: DebateContext,
        add_debug: Optional[Callable[[str], None]] = None
    ) -> DebateResult:
        """
        Pattern B: Auto-Consensus

        Iterates until Sokrates says LGTM or max_rounds reached.
        Checks for user interjections between rounds.
        """
        if add_debug:
            add_debug(f"🤝 Multi-Agent: Auto-Konsens Modus (max {ctx.max_rounds} Runden)")

        debate_history: List[Dict[str, str]] = []
        alfred_answer = ""
        sokrates_critique = ""

        for round_num in range(1, ctx.max_rounds + 1):
            if add_debug:
                add_debug(f"🔄 Debate Runde {round_num}/{ctx.max_rounds}")

            # Step 1: AIfred answers (or refines based on critique)
            if round_num == 1:
                alfred_messages = self._build_messages(ctx.history, ctx.query)
            else:
                # Check for user interjection
                user_input = ""
                if ctx.get_user_interjection:
                    user_input = ctx.get_user_interjection()
                    if user_input and add_debug:
                        add_debug(f"💬 User-Einwurf: {user_input[:50]}...")

                user_interjection_text = f"\n\nUser-Einwurf: {user_input}" if user_input else ""

                refinement_prompt = self._get_refinement_prompt(
                    critique=sokrates_critique,
                    user_interjection=user_interjection_text
                )

                alfred_messages = self._build_messages(ctx.history, ctx.query)
                alfred_messages.append({"role": "assistant", "content": alfred_answer})
                alfred_messages.append({"role": "user", "content": refinement_prompt})

            alfred_response = await ctx.llm_client.chat(ctx.model, alfred_messages, ctx.options)
            alfred_answer = alfred_response.text
            debate_history.append({"role": "alfred", "round": round_num, "content": alfred_answer})

            if add_debug:
                add_debug(f"🎩 AIfred R{round_num}: {len(alfred_answer)} Zeichen")

            # Step 2: Sokrates critiques
            sokrates_messages = [
                {"role": "system", "content": self._get_critic_prompt()},
                {"role": "user", "content": f"Frage des Users: {ctx.query}"},
                {"role": "assistant", "content": f"AIfred's Antwort (Runde {round_num}):\n{alfred_answer}"},
                {"role": "user", "content": "Analysiere diese Antwort kritisch."}
            ]
            sokrates_response = await ctx.llm_client.chat(ctx.model, sokrates_messages, ctx.options)
            sokrates_critique = sokrates_response.text
            debate_history.append({"role": "sokrates", "round": round_num, "content": sokrates_critique})

            if add_debug:
                add_debug(f"🧠 Sokrates R{round_num}: {len(sokrates_critique)} Zeichen")

            # Check for consensus
            if "LGTM" in sokrates_critique.upper():
                if add_debug:
                    add_debug(f"✅ Konsens erreicht in Runde {round_num}")
                return DebateResult(
                    alfred_answer=alfred_answer,
                    sokrates_critique=sokrates_critique,
                    rounds_used=round_num,
                    consensus_reached=True,
                    debate_history=debate_history
                )

        # Max rounds reached without consensus
        if add_debug:
            add_debug(f"⚠️ Max Runden erreicht ohne Konsens")

        return DebateResult(
            alfred_answer=alfred_answer,
            sokrates_critique=sokrates_critique,
            rounds_used=ctx.max_rounds,
            consensus_reached=False,
            debate_history=debate_history
        )

    async def devils_advocate(
        self,
        ctx: DebateContext,
        add_debug: Optional[Callable[[str], None]] = None
    ) -> DebateResult:
        """
        Pattern C: Devil's Advocate

        AIfred answers, then Sokrates provides Pro and Contra arguments.
        """
        if add_debug:
            add_debug("🤝 Multi-Agent: Advocatus Diaboli Modus")

        # Step 1: AIfred answers
        alfred_messages = self._build_messages(ctx.history, ctx.query)
        alfred_response = await ctx.llm_client.chat(ctx.model, alfred_messages, ctx.options)
        alfred_answer = alfred_response.text

        if add_debug:
            add_debug(f"🎩 AIfred: {len(alfred_answer)} Zeichen generiert")

        # Step 2: Sokrates provides Pro/Contra analysis
        sokrates_messages = [
            {"role": "system", "content": self._get_devils_advocate_prompt()},
            {"role": "user", "content": f"""Frage des Users: {ctx.query}

AIfred's Antwort/Position:
{alfred_answer}

Analysiere diese Position mit Pro- und Contra-Argumenten."""}
        ]
        sokrates_response = await ctx.llm_client.chat(ctx.model, sokrates_messages, ctx.options)
        sokrates_analysis = sokrates_response.text

        if add_debug:
            add_debug(f"🧠 Sokrates: Pro/Contra Analyse ({len(sokrates_analysis)} Zeichen)")

        # Parse Pro/Contra sections
        pro_args, contra_args = self._parse_pro_contra(sokrates_analysis)

        return DebateResult(
            alfred_answer=alfred_answer,
            sokrates_pro=pro_args,
            sokrates_contra=contra_args,
            rounds_used=1,
            consensus_reached=True,
            debate_history=[
                {"role": "alfred", "content": alfred_answer},
                {"role": "sokrates", "content": sokrates_analysis}
            ]
        )

    def _build_messages(
        self,
        history: List[Dict[str, str]],
        query: str
    ) -> List[Dict[str, str]]:
        """Build message list from history and current query"""
        messages = []

        # Add history (if any)
        for msg in history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })

        # Add current query
        messages.append({"role": "user", "content": query})

        return messages

    def _parse_pro_contra(self, analysis: str) -> tuple[str, str]:
        """Parse Pro and Contra sections from Sokrates' analysis"""
        pro_args = ""
        contra_args = ""

        # Try to find Pro section
        lower_analysis = analysis.lower()

        # Find Pro section
        pro_markers = ["## pro", "**pro", "pro:", "pro-argumente:", "pro arguments:"]
        contra_markers = ["## contra", "**contra", "contra:", "contra-argumente:", "contra arguments:"]

        pro_start = -1
        contra_start = -1

        for marker in pro_markers:
            idx = lower_analysis.find(marker)
            if idx != -1 and (pro_start == -1 or idx < pro_start):
                pro_start = idx

        for marker in contra_markers:
            idx = lower_analysis.find(marker)
            if idx != -1 and (contra_start == -1 or idx < contra_start):
                contra_start = idx

        if pro_start != -1 and contra_start != -1:
            if pro_start < contra_start:
                # Pro comes first
                pro_args = analysis[pro_start:contra_start].strip()
                contra_args = analysis[contra_start:].strip()
            else:
                # Contra comes first
                contra_args = analysis[contra_start:pro_start].strip()
                pro_args = analysis[pro_start:].strip()
        elif pro_start != -1:
            pro_args = analysis[pro_start:].strip()
        elif contra_start != -1:
            contra_args = analysis[contra_start:].strip()
        else:
            # No clear sections - return full analysis as pro
            pro_args = analysis.strip()

        return pro_args, contra_args
