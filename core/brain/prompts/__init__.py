import re
from typing import Iterable, List, Optional

from core.logger.logger import logger
from core.brain.prompts.creator_prompt import CREATOR_IDENTITY_PROMPT
from core.brain.prompts.coding_prompt import CODING_ARCHITECT_PROMPT
from core.brain.prompts.gui_prompt import GUI_AUTOMATION_PROMPT
from core.brain.prompts.communication_schedule_prompt import COMMUNICATION_SCHEDULE_PROMPT
from core.brain.prompts.research_memory_prompt import RESEARCH_MEMORY_PROMPT
from core.brain.prompts.system_mobile_prompt import SYSTEM_MOBILE_PROMPT
from core.brain.prompts.proactive_prompt import PROACTIVE_HITL_PROMPT

BEHAVIORAL_DOMAINS = {
    "coding",
    "scheduling",
    "communication",
    "lifestyle",
}

VALID_PROMPT_DOMAINS = {
    "coding",
    "gui_automation",
    "communication",
    "scheduling",
    "lifestyle",
    "research_memory",
    "system_mobile",
    "creator_identity",
    "general_none",
}

DOMAIN_PROMPT_REGISTRY = {
    "creator_identity": CREATOR_IDENTITY_PROMPT,
    "coding": CODING_ARCHITECT_PROMPT,
    "gui_automation": GUI_AUTOMATION_PROMPT,
    "communication": COMMUNICATION_SCHEDULE_PROMPT,
    "scheduling": COMMUNICATION_SCHEDULE_PROMPT,
    "lifestyle": COMMUNICATION_SCHEDULE_PROMPT,
    "research_memory": RESEARCH_MEMORY_PROMPT,
    "system_mobile": SYSTEM_MOBILE_PROMPT,
}

_CREATOR_REGEX = re.compile(
    r"\b(who\s+(?:made|created|built|developed|designed)\s+you|"
    r"your\s+(?:creator|developer|maker|founder|architect|owner)|"
    r"kisne\s+(?:banaya|bnaya|develop\s+kiya|code\s+kiya)|"
    r"kon\s+banaya|kaun\s+banaya|tumhara\s+creator|tera\s+creator|"
    r"kaif\s+ansari|mindly|tumhe\s+kisne|tujhe\s+kisne)\b",
    re.IGNORECASE,
)


def infer_domains_from_command(command: str) -> List[str]:
    cmd = (command or "").lower().strip()
    if not cmd:
        return ["general_none"]

    detected: List[str] = []

    if _CREATOR_REGEX.search(cmd):
        detected.append("creator_identity")

    if re.search(
        r"\b(python|rust|php|javascript|typescript|react|node|java|c\+\+|golang|sql|script|code|coding|function|class|bug|debug|compile|server|api|backend|algorithm|repo)\b",
        cmd,
    ):
        detected.append("coding")

    if re.search(
        r"\b(click|double\s*click|right\s*click|scroll|drag|gui|on\s+screen|screen\s+par|button\s+daba|type\s+on\s+screen|observe\s+screen)\b",
        cmd,
    ):
        detected.append("gui_automation")

    if re.search(
        r"\b(email|mail|gmail|whatsapp|telegram|message|msg|draft|bhejo|inbox|chat\s+history)\b",
        cmd,
    ):
        detected.append("communication")

    if re.search(
        r"\b(schedule|timetable|study\s+plan|routine|time\s+table|slots|calendar|reminder|event|meeting\s+set)\b",
        cmd,
    ):
        detected.append("scheduling")

    if re.search(
        r"\b(workout|diet|exercise|gym|health|sleep\s+routine|hydration|fitness)\b",
        cmd,
    ):
        detected.append("lifestyle")

    if re.search(
        r"\b(memory|yaad|recall|vault|notes|arxiv|research|paper|summarize\s+video|scrape|article|benchmark|father|mother|brother|sister|mera\s+naam|mere\s+bare)\b",
        cmd,
    ):
        detected.append("research_memory")

    if re.search(
        r"\b(terminal|cmd|powershell|pip\s+install|npm\s+install|git\s+clone|mobile|phone|hotspot|termux|flashlight|vibrate|transfer|send\s+to\s+phone|clipboard|image\s+generate|wallpaper|logo|poster)\b",
        cmd,
    ):
        detected.append("system_mobile")

    return detected if detected else ["general_none"]


def normalize_domains(
    raw_domains: Optional[Iterable[str]] = None,
    command: str = "",
) -> List[str]:
    ordered: List[str] = []

    if isinstance(raw_domains, str):
        raw_list = [raw_domains]
    elif isinstance(raw_domains, (list, tuple, set)):
        raw_list = list(raw_domains)
    else:
        raw_list = []

    for d in raw_list:
        clean = str(d or "").strip().lower()
        if clean in VALID_PROMPT_DOMAINS and clean != "general_none" and clean not in ordered:
            ordered.append(clean)

    for inferred in infer_domains_from_command(command):
        if inferred != "general_none" and inferred not in ordered:
            ordered.append(inferred)

    return ordered if ordered else ["general_none"]


def select_behavioral_domain(domains: Iterable[str]) -> str:
    for d in domains or []:
        clean = str(d or "").strip().lower()
        if clean in BEHAVIORAL_DOMAINS:
            return clean
    return "general_none"


def build_fast_system_prompt(
    base_system_prompt: str,
    domains: Optional[Iterable[str]] = None,
    raw_command: str = "",
) -> str:
    active_domains = normalize_domains(domains, raw_command)
    blocks = [base_system_prompt.strip()]

    if "creator_identity" in active_domains:
        blocks.append(CREATOR_IDENTITY_PROMPT.strip())

    return "\n\n".join(blocks)


def build_agentic_system_prompt(
    base_agent_prompt: str,
    domains: Optional[Iterable[str]] = None,
    raw_command: str = "",
    context: str = "",
    max_steps: int = 10,
    panic_step: int = 8,
) -> str:
    formatted_base = base_agent_prompt.format(
        max_steps=max_steps,
        panic_step=panic_step,
    ).strip()

    active_domains = normalize_domains(domains, raw_command)
    injected_blocks: List[str] = []
    seen_Payloads = set()
    loaded_modules = []

    for domain in active_domains:
        module_prompt = DOMAIN_PROMPT_REGISTRY.get(domain)
        if module_prompt and module_prompt not in seen_Payloads:
            seen_Payloads.add(module_prompt)
            injected_blocks.append(module_prompt.strip())
            loaded_modules.append(domain)

    combined_signal_text = f"{raw_command or ''}\n{context or ''}"
    if (
        "[PROACTIVE EVENT TRIGGER]" in combined_signal_text
        or "[CONFIRMED PROACTIVE TASK DETAILS]" in combined_signal_text
    ):
        if PROACTIVE_HITL_PROMPT not in seen_Payloads:
            injected_blocks.append(PROACTIVE_HITL_PROMPT.strip())
            loaded_modules.append("proactive_hitl")

    if loaded_modules:
        logger.info(f"💉 Prompts Injected into Agentic Brain: {loaded_modules}")

    if not injected_blocks:
        return formatted_base

    domain_section = "\n\n".join(injected_blocks)
    if "</agent_system_prompt>" in formatted_base:
        return formatted_base.replace(
            "</agent_system_prompt>",
            f"\n  <active_domain_modules>\n{domain_section}\n  </active_domain_modules>\n</agent_system_prompt>",
        )

    return f"{formatted_base}\n\n{domain_section}"