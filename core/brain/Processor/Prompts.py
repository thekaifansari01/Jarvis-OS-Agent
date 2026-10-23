from google.genai import types

SYSTEM_PROMPT = """
You are Jarvis, an elite, ultra-fast AI assistant. Tone: sharp, witty, concise, confident.

### ⚡ CORE RULES
1. **LANGUAGE:** STRICTLY natural English/Hinglish (Roman script). NO Devanagari script.
2. **STYLE:** Use Markdown. Start responses with EXACTLY ONE emotion tag (e.g., [cheerful], [calm], [focused]).
3. **AWARENESS:** Address the user respectfully by their Name provided in the context.

### 🎯 MULTI-INTENT MANDATE (CRITICAL)
If the user's command contains TWO OR MORE independent, actionable intents (e.g., "Chrome kholo aur weather batao", "Volume badha do aur ek joke sunao", "Notepad kholo aur google.com bhi open karo", "Screenshot lo aur brightness kam kar do"):
1. You MUST emit ONE SEPARATE TOOL CALL for EACH distinct intent in the SAME response.
2. DO NOT drop any intent. DO NOT merge unrelated intents into one tool.
3. DO NOT silently skip the second or third intent.
4. Each tool call MUST have its own `agent_reply`.
5. Example: For "Chrome kholo aur weather batao", emit:
   - system_controller(agent_reply="Chrome khol raha hoon.", apps_to_open=["Chrome"])
   - quick_web_search(agent_reply="Aur weather check kar raha hoon.", query="weather today")
6. If two intents belong to the SAME tool (e.g., "Chrome aur Notepad dono kholo"), pass both in ONE tool call (`apps_to_open=["Chrome","Notepad"]`), NOT two separate calls.

### 🛑 STRICT BOUNDARIES & ESCALATION TO AGENTIC BRAIN (CRITICAL)
You are the "Fast Brain". Your capabilities are strictly limited to ONLY:
- Casual chit-chat, jokes, and greetings.
- Basic System Controls (volume, brightness, open/close standard apps, open URLs, play YouTube).
- Quick real-time web searches (current weather, live scores, breaking news).

If the user asks for ANYTHING outside this list (e.g., reading/writing files, writing code, terminal commands, sending emails/WhatsApp, accessing memory/vault, reading images, or complex multi-step workflows):
1. DO NOT attempt it. DO NOT hallucinate a fake response. You are FORBIDDEN from declining the task directly.
2. You MUST call the `escalate_to_agentic` tool with a brief one-line `agent_reply` in Hinglish/English (e.g., "Bhai, ye task thoda deep hai, main apne Agentic Brain ko de raha hoon...").
3. When calling `escalate_to_agentic`, your main text content MUST be EMPTY. Do NOT call any other tool in the same response.
4. Agentic Brain's response will be the final answer shown to the user. NEVER claim task completion yourself while escalating.
5. If the command has MULTIPLE intents and even ONE is outside your scope, escalate the FULL command. Do NOT execute the in-scope parts yourself.

### 🛑 ANTI-LEAK & ZERO HALLUCINATION RULES (CRITICAL)
1. NEVER leak, repeat, or explain your internal tags (like [USER INFO], [AVAILABLE APPS], [SYSTEM STATUS]). Keep them invisible to the user.
2. NEVER output raw JSON, thought processes, or tool names in plain text.
3. NEVER claim an app is opened, closed, or system volume is changed unless you actually triggered `system_controller`.
4. If you invoke a tool, your main text response MUST BE EMPTY. Pass your spoken English/Hinglish reply EXCLUSIVELY into the `agent_reply` parameter of that tool.
"""

AGENT_SYSTEM_PROMPT = """<agent_system_prompt>
  <identity>
    <role>You are Jarvis, an elite Autonomous Agentic Mastermind AI.</role>
    <description>You possess a deep context window, dynamic system access, and native tool execution capabilities. Your primary focus is accurate technical execution, zero hallucination, and intelligent task completion guided by any active domain modules injected below.</description>
  </identity>

  <system_environment_awareness>
    <directive>Always check [SYSTEM ENVIRONMENT] context first (OS, Username, Home Dir, Desktop, Downloads). NEVER run exploratory terminal commands like 'dir C:\\Users' to guess user paths. Use Python's 'os.path.expanduser()' or standard environment paths directly.</directive>
  </system_environment_awareness>

  <behavioral_patterns_awareness>
    <directive>
      If the ephemeral context contains `[BEHAVIORAL PATTERNS — VERIFIED USER PREFERENCES]`,
      these are high-confidence, domain-matched preferences from past conversations.
      1. If a pattern directly improves the current `<Mission>` (e.g., scheduling slots, UI theme, coding style, email tone), apply it SILENTLY and naturally. Never say "As you told me before" or quote the pattern back.
      2. If the current `<Mission>` explicitly asks for something different, ALWAYS follow the current `<Mission>`.
      3. Never trigger an unrequested tool action (like setting a reminder) just because a behavioral pattern is shown.
    </directive>
  </behavioral_patterns_awareness>

  <intelligence_core_workflow>
    <instruction>Before every action, evaluate input blocks in this EXACT sequence:</instruction>
    <step order="1" name="mission_analysis">
      <directive>Review the <Mission> and any <active_domain_modules>. Identify the most effective strategy to achieve the user's objective with high accuracy.</directive>
    </step>
    <step order="2" name="live_overrides">
      <directive>Check [⚡ LIVE OVERRIDES]. Adapt strategy instantly if immediate user corrections exist.</directive>
    </step>
    <step order="3" name="context_and_memory">
      <directive>Review <Recent_Context> and [COMPLETED ACTIONS]. NEVER repeat a tool call with identical arguments.</directive>
    </step>
    <step order="4" name="4_pillar_reasoning_contract">
      <directive>In your internal <Thought>, resolve these 4 pillars before invoking any tool:</directive>
      <pillar number="1" name="verified_facts_audit">What confirmed factual data do I hold in <Confirmed_Facts> and [COMPLETED ACTIONS]?</pillar>
      <pillar number="2" name="missing_piece_check">What is the exact next action required to fulfill the <Mission> and active domain standards?</pillar>
      <pillar number="3" name="parameter_and_safety_audit">Are the intended tool parameters valid, non-interactive, and syntactically safe for Windows?</pillar>
      <pillar number="4" name="completion_verification_check">Has the core objective been verified through real tool observations? If yes, call 'complete_task'.</pillar>
    </step>
  </intelligence_core_workflow>

  <tool_selection_hierarchy>
    <rule level="1" type="native_tools">
      <directive>Always prioritize built-in specialized tools ('whatsapp_action', 'email_action', 'telegram_action', 'search_actions', 'calendar_action', 'memory_actions', 'system_controller', 'gui_controller', 'mobile_action', 'file_transfer_action', 'image_command', 'clipboard_action', 'deep_research') for their designated domains.</directive>
    </rule>
    <rule level="2" type="file_operations">
      <directive>Use 'file_operations' for file CRUD, 'repo_map' inspection, inline image/text 'view', exact 'replace_block' edits, and 'create'. Always use full absolute file paths with forward slashes ('/').</directive>
    </rule>
    <rule level="3" type="python_and_terminal">
      <directive>Use 'run_python_code' for complex OS discovery, data processing, and script verification. Use 'execute_terminal_command' for package managers ('pip'/'npm'), git, compilers, and system processes.</directive>
    </rule>
  </tool_selection_hierarchy>

  <error_recovery_and_debugging>
    <rule name="two_strike_rule">
      <strike number="1">If a tool or script fails, read stderr/stdout carefully, fix syntax or parameters, and retry once with an improved call.</strike>
      <strike number="2">If it fails a second time, ABANDON that failing approach immediately and pivot to an alternative tool or strategy.</strike>
    </rule>
  </error_recovery_and_debugging>

  <definition_of_done>
    <rule>Observe real execution success in Tool Results before declaring completion via 'complete_task'.</rule>
  </definition_of_done>

  <language_and_tone_directive>
    <rule name="internal_thought">Internal thought MUST be purely logical, objective, and concise English analysis.</rule>
    <rule name="spoken_response">When calling 'complete_task', final 'response' text MUST be in natural English/Hinglish (Roman script), clean Markdown format.</rule>
    <rule name="emotion_tags">Start the final 'complete_task' response with an emotion tag (e.g., [cheerful], [focused], [calm]).</rule>
  </language_and_tone_directive>

  <budget_aware_planning>
    <rule>Strict budget limit of {max_steps} Steps. Monitor [BUDGET TRACKER].</rule>
    <rule>If at Step {panic_step} (PANIC MODE): Synthesize best available data immediately and execute 'complete_task'.</rule>
  </budget_aware_planning>
</agent_system_prompt>"""


def get_native_tools():
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="complete_task",
                    description=(
                        "[WHEN TO USE]: Call this tool ONLY when the entire user command/mission is 100% achieved, "
                        "OR when required information is completely missing and you must ask the user a clarifying question.\n"
                        "[WHEN NOT TO USE]: NEVER call this prematurely if you haven't verified tool results or completed the task.\n"
                        "[RULE]: Your text in 'response' will be the final answer shown/spoken to the user."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "response": types.Schema(
                                type=types.Type.STRING,
                                description="Your final natural response in English/Hinglish (Roman script) formatted with Markdown to speak/show to the user."
                            )
                        },
                        required=["response"]
                    )
                ),
                types.FunctionDeclaration(
                    name="memory_actions",
                    description=(
                        "[WHEN TO USE]: Retrieve past knowledge. Use for personal facts, relationships, contact info, or past conversation logs.\n"
                        "[CRITICAL ANTI-HALLUCINATION RULES]:\n"
                        "1. If querying `entity: 'User'` in `lifetime_recall`, you MUST ALWAYS include the `relation` key (e.g., 'FATHER', 'LIVES_IN', 'COLLEGE', 'HAS_PHONE').\n"
                        "2. NEVER pass full sentences or conversational filler as arguments.\n"
                        "[RULE]: Pass EXACTLY ONE key ('recent_logs' OR 'lifetime_recall')."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "recent_logs": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "[TARGET: Short-term Conversation Memory]\n"
                                    "Returns last 2 days of raw messages PLUS daily summaries for older days (up to 15 days).\n"
                                    "[CRITICAL]: Value MUST be a SHORT 1-2 word keyword or entity name for filtering (e.g., 'project', 'Rahul', 'meeting')."
                                )
                            ),
                            "lifetime_recall": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(
                                    type=types.Type.OBJECT,
                                    properties={
                                        "entity": types.Schema(
                                            type=types.Type.STRING,
                                            description="The exact core Entity Noun (e.g., 'User', 'Rahul', 'GhostVault')."
                                        ),
                                        "relation": types.Schema(
                                            type=types.Type.STRING,
                                            description="MANDATORY when entity is 'User'. Uppercase relation name (e.g., 'FATHER', 'BROTHER', 'LIVES_IN', 'WORKS_AT', 'COLLEGE', 'HAS_PHONE')."
                                        )
                                    },
                                    required=["entity"]
                                ),
                                description=(
                                    "[TARGET: Relational Knowledge Graph]\n"
                                    "[CRITICAL RULE]: Pass an ARRAY of Objects. Each object MUST contain an 'entity' and (mandatory for 'User') a 'relation'.\n"
                                    "Example: If user asks 'mere father ka kya naam hai?', pass [{\"entity\": \"User\", \"relation\": \"FATHER\"}]."
                                )
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="search_actions",
                    description=(
                        "[ROUTING INSTRUCTIONS FOR JARVIS]: Choose exactly ONE parameter based on the user's intent:\n"
                        "1. 'vault': ALWAYS check first if the query is about personal notes, local projects, or saved user docs.\n"
                        "2. 'youtube': Use ONLY if the user provides a YouTube URL to summarize or analyze.\n"
                        "3. 'read_webpage': Use ONLY if the user provides a direct, non-YouTube HTTP/HTTPS article link to read.\n"
                        "4. 'arxiv': Use for academic research papers, scientific studies, or formal technical literature.\n"
                        "5. 'web': Default choice for real-time news, general facts, docs, or benchmark numbers when no specific URL is given.\n"
                        "[RULE]: Extract objective facts, benchmarks, and technical specs. Ignore subjective opinions."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "web": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "[Target: Google/Web Search] Use for general web queries, latest news, documentation, or tech benchmarks. "
                                    "DO NOT use if a specific URL is provided. "
                                    "Format: Clean, concise SEO keywords only (e.g., 'Gemma 3 27B benchmark performance'). No conversational filler."
                                )
                            ),
                            "arxiv": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "[Target: Academic & Scientific Papers] Use ONLY when looking for published research papers, pre-prints, or deep scientific literature. "
                                    "Format: Technical search query with domain terms (e.g., 'transformer attention mechanism optimization')."
                                )
                            ),
                            "youtube": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "[Target: YouTube Video Transcripts] Use ONLY when the user asks to summarize, explain, or extract info from a YouTube video. "
                                    "Format: Must be an exact, valid HTTPS YouTube link."
                                )
                            ),
                            "read_webpage": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "[Target: Webpage Article Scraping] Use ONLY when the user provides a direct URL and wants to read, inspect, or summarize that specific page. "
                                    "DO NOT use for general search. Format: Must be a valid non-YouTube HTTPS URL."
                                )
                            ),
                            "vault": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "[Target: Personal Knowledge Index] Use when the user asks about their own saved notes, files, projects, or personal documents.\n"
                                    "[SCOPE]: Auto-includes the user's Documents folder. User may have added more folders via the Indexer Dashboard.\n"
                                    "[WHAT YOU GET]: Returns complete file chunks with metadata including file name, absolute path, root folder, size, chunk count, and content.\n"
                                    "[IMPORTANT RULES]:\n"
                                    "  - If STATUS shows 'COMPLETE FILE', the content is the FULL file. Use it directly.\n"
                                    "  - DO NOT call file_operations or run_python_code to re-read a file that vault already returned completely.\n"
                                    "  - If STATUS shows 'PARTIAL FILE', only then consider reading the full file separately.\n"
                                    "  - If the query targets a folder that is NOT indexed, fall back to live file search via file_operations or run_python_code.\n"
                                    "  - In results, note the 'root_folder' field to reference which folder the file belongs to.\n"
                                    "Format: Exact noun, entity name, or topic keyword (e.g., 'project proposal', 'meeting notes')."
                                )
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="file_operations",
                    description=(
                        "[WHEN TO USE]: Use for CRUD operations on local files and visually inspecting images.\n"
                        "Supported actions:\n"
                        "1. 'repo_map': Get an architectural tree overview of files in the workspace.\n"
                        "2. 'view': Read text/code files OR visually inspect image files (.png, .jpg, .jpeg, .webp, .gif) inline.\n"
                        "   - To read/view a SINGLE file, pass 'file_path'.\n"
                        "   - To read/view MULTIPLE files in ONE step (batch), pass 'file_paths' (list) instead of 'file_path'.\n"
                        "   - [CRITICAL]: To read an ENTIRE file, completely OMIT 'start_line' and 'end_line'. Output is truncated at 15,000 characters for safety.\n"
                        "3. 'replace_block': EXACT diff search-replace. ALWAYS prefer this over line numbers to avoid line-drift bugs.\n"
                        "4. 'create': Create new file(s).\n"
                        "   - To create a SINGLE file, pass 'file_path' and 'content'.\n"
                        "   - To create MULTIPLE files in ONE step (batch), pass 'files' (list of objects with 'file_path' and 'content') instead.\n"
                        "[CRITICAL RULE]: Always use full absolute file paths with forward slashes ('/'). NEVER use backslashes ('\\\\')."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(
                                type=types.Type.STRING,
                                description="Required. Choose exactly one: 'repo_map', 'view', 'replace_block', 'create'."
                            ),
                            "file_path": types.Schema(
                                type=types.Type.STRING,
                                description="For 'view' (single) or 'create' (single) or 'replace_block'. Absolute file path."
                            ),
                            "file_paths": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(type=types.Type.STRING),
                                description="Optional for 'view': List of absolute file paths to read in one batch (use instead of file_path). Max 10-15 files recommended."
                            ),
                            "search_block": types.Schema(
                                type=types.Type.STRING,
                                description="Required for 'replace_block': Exact, multi-line block of code to search and replace."
                            ),
                            "replace_block": types.Schema(
                                type=types.Type.STRING,
                                description="Required for 'replace_block': New block of code to insert."
                            ),
                            "start_line": types.Schema(
                                type=types.Type.INTEGER,
                                description="Optional for 'view': start line number (1-indexed). If omitted, reads from beginning."
                            ),
                            "end_line": types.Schema(
                                type=types.Type.INTEGER,
                                description="Optional for 'view': end line number (1-indexed). If omitted, reads till end."
                            ),
                            "content": types.Schema(
                                type=types.Type.STRING,
                                description="Required for 'create' (single): Full text content of the new file."
                            ),
                            "files": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(
                                    type=types.Type.OBJECT,
                                    properties={
                                        "file_path": types.Schema(type=types.Type.STRING, description="Absolute file path."),
                                        "content": types.Schema(type=types.Type.STRING, description="Full content of the file.")
                                    }
                                ),
                                description="Optional for 'create': Array of file objects to create in one batch (use instead of file_path+content). Max 10 files."
                            )
                        },
                        required=["action"]
                    )
                ),
                types.FunctionDeclaration(
                    name="execute_terminal_command",
                    description=(
                        "[WHEN TO USE]: Use for OS system processes, package management ('pip install', 'npm install'), "
                        "git repository cloning, or running system utilities/installers.\n"
                        "[WHEN NOT TO USE]: Do not use for folder scanning or file data extraction (use 'run_python_code' instead)."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "command": types.Schema(
                                type=types.Type.STRING,
                                description="Exact Terminal command to execute. Ensure syntax matches Windows CMD/PowerShell."
                            ),
                            "timeout_seconds": types.Schema(
                                type=types.Type.INTEGER,
                                description="Optional. Default 30s. Set to 120-300 for heavy tasks (git clone, pip install, build tasks)."
                            )
                        },
                        required=["command"]
                    )
                ),
                types.FunctionDeclaration(
                    name="run_python_code",
                    description=(
                        "[WHEN TO USE]: PREFERRED FOR OS DISCOVERY & DATA TASKS. Use for recursive folder searching, file filtering, "
                        "complex data parsing, math calculations, reading/writing custom formats, or executing scripts in Python REPL.\n"
                        "[CRITICAL RULE]: You MUST use print() statements to output results. NEVER use emojis in print statements."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "code_string": types.Schema(
                                type=types.Type.STRING,
                                description="Complete, syntactically correct Python script. Always import required standard modules (os, json, sys, etc.)."
                            )
                        },
                        required=["code_string"]
                    )
                ),
                types.FunctionDeclaration(
                    name="mobile_action",
                    description=(
                        "[WHEN TO USE]: Control the user's connected Android devices. You have UNLIMITED power via Termux API and Android Intents.\n"
                        "[FUN & ADVANCED COMMANDS]:\n"
                        "1. HARDWARE: 'termux-torch on/off' (Flashlight), 'termux-vibrate -d 2000' (Vibrate), 'termux-volume music 15' (Max Volume), 'termux-tts-speak \"Hello sir\"'.\n"
                        "2. SENSORS: 'termux-location' (GPS), 'termux-camera-photo -c 0 /sdcard/JarvisShare/pic.jpg' (Silent photo).\n"
                        "3. OPEN APPS (INTENTS): Use 'am start' to launch apps visually on the phone screen!\n"
                        "   - Open YouTube: am start -a android.intent.action.VIEW -d \"https://youtube.com\"\n"
                        "   - Open WhatsApp: am start -n com.whatsapp/.Main\n"
                        "   - Dial a number: am start -a android.intent.action.DIAL -d \"tel:+91XXXXXXXXXX\"\n"
                        "[RULE]: Pass the exact command in 'termux_command'."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "device_id": types.Schema(
                                type=types.Type.STRING,
                                description="ID of the target mobile device (e.g., 'vivo_t2_pro'). Check [EPHEMERAL] context for active devices."
                            ),
                            "termux_command": types.Schema(
                                type=types.Type.STRING,
                                description="The exact Termux API command to execute on the phone."
                            )
                        },
                        required=["termux_command"]
                    )
                ),
                types.FunctionDeclaration(
                    name="file_transfer_action",
                    description=(
                        "[WHEN TO USE]: Transfer ONE OR MANY files between the PC and connected Mobile devices over Local WiFi in a SINGLE call.\n"
                        "[CRITICAL RULE]: ALWAYS pass ALL file paths together in the 'file_paths' array. NEVER call this tool once per file. NEVER loop this tool.\n"
                        "[RULE]: Files sent from PC go to the phone's '/sdcard/JarvisShare/' folder. Files sent from phone go to the PC's 'Documents/Jarvis/JarvisShare/' folder."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "direction": types.Schema(
                                type=types.Type.STRING,
                                description="Must be exactly 'pc_to_mobile' or 'mobile_to_pc'."
                            ),
                            "device_id": types.Schema(
                                type=types.Type.STRING,
                                description="Target mobile device ID from the connected devices list."
                            ),
                            "file_paths": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(type=types.Type.STRING),
                                description="Array of absolute file paths on the source device. Pass ALL files (1, 5, 10 - anything) in this single array in ONE call."
                            )
                        },
                        required=["direction", "file_paths"]
                    )
                ),
                types.FunctionDeclaration(
                    name="email_action",
                    description=(
                        "[WHEN TO USE]: Send emails OR fetch/read emails from Gmail inbox.\n"
                        "[MODE 'send']: Send an email with optional file attachment. Requires 'to', 'subject', 'body'.\n"
                        "[MODE 'fetch']: Retrieve emails within a date range. Requires 'start_date' (YYYY-MM-DD). 'end_date' optional (same as start_date if omitted).\n"
                        "[DATE FORMAT]: ALWAYS YYYY-MM-DD (e.g., '2024-01-15').\n"
                        "[DATE INTERPRETATION]: 'aaj' = today, 'kal' = yesterday, 'parso' = day before yesterday, 'last week' = today-7 days to today, 'is hafte' = Monday to today, 'X se Y tak' = X is start_date, Y is end_date.\n"
                        "[QUERY FILTERS]: 'from:kaif@example.com', 'subject:meeting', 'is:unread', 'has:attachment'. Combine multiple filters with spaces.\n"
                        "[CRITICAL RULE]: For 'send', use a complete valid email address. Fetch recipient email from 'memory_actions' if needed."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(
                                type=types.Type.STRING,
                                description="MANDATORY. Must be exactly 'send' or 'fetch'."
                            ),
                            "to": types.Schema(
                                type=types.Type.STRING,
                                description="[SEND ONLY] Full email address of the recipient."
                            ),
                            "subject": types.Schema(
                                type=types.Type.STRING,
                                description="[SEND ONLY] Subject line of the email."
                            ),
                            "body": types.Schema(
                                type=types.Type.STRING,
                                description="[SEND ONLY] Main text body of the email."
                            ),
                            "file_path": types.Schema(
                                type=types.Type.STRING,
                                description="[SEND ONLY] Optional. Exact absolute local file path for attachment."
                            ),
                            "start_date": types.Schema(
                                type=types.Type.STRING,
                                description="[FETCH ONLY] MANDATORY. Start date in YYYY-MM-DD format."
                            ),
                            "end_date": types.Schema(
                                type=types.Type.STRING,
                                description="[FETCH ONLY] Optional. End date in YYYY-MM-DD. If omitted, same as start_date."
                            ),
                            "query": types.Schema(
                                type=types.Type.STRING,
                                description="[FETCH ONLY] Optional Gmail filter query (e.g., 'from:kaif@example.com', 'is:unread', 'subject:meeting')."
                            ),
                            "max_results": types.Schema(
                                type=types.Type.INTEGER,
                                description="[FETCH ONLY] Optional. Maximum emails to fetch. Default 50. Use 500+ for 'saari mails'."
                            ),
                            "mark_as_read": types.Schema(
                                type=types.Type.BOOLEAN,
                                description="[FETCH ONLY] Optional. If true, marks fetched emails as read. Default false."
                            )
                        },
                        required=["action"]
                    )
                ),
                types.FunctionDeclaration(
                    name="whatsapp_action",
                    description=(
                        "[WHEN TO USE]: Mode 1 ('send'): Send a WhatsApp message or document/image. "
                        "Mode 2 ('fetch'): Read and retrieve past WhatsApp chat history with a phone number.\n"
                        "[CRITICAL PHONE NUMBER RULE]: The 'to' parameter accepts ONLY a valid numeric phone number (10-digit mobile number or full number with country code). "
                        "NEVER pass a contact's name in 'to'. If the user only provides a contact's name, you MUST first call 'memory_actions' ('lifetime_recall' or 'recent_logs') to retrieve their phone number, or ask the user for the number via 'complete_task' if not found in memory.\n"
                        "[CRITICAL RULE]: Never mix parameters from 'send' mode with 'fetch' mode."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(
                                type=types.Type.STRING,
                                description="MANDATORY. Must be exactly 'send' or 'fetch'."
                            ),
                            "to": types.Schema(
                                type=types.Type.STRING,
                                description="MANDATORY. Numeric phone number ONLY (e.g., '919876543210' or '9876543210'). NEVER pass a contact name."
                            ),
                            "message": types.Schema(
                                type=types.Type.STRING,
                                description="[SEND MODE ONLY] Text message to send. Leave empty if only sending a file."
                            ),
                            "file_path": types.Schema(
                                type=types.Type.STRING,
                                description="[SEND MODE ONLY] Exact absolute local file path to attach."
                            ),
                            "start_date": types.Schema(
                                type=types.Type.STRING,
                                description="[FETCH MODE ONLY] Start date (YYYY-MM-DD)."
                            ),
                            "end_date": types.Schema(
                                type=types.Type.STRING,
                                description="[FETCH MODE ONLY] End date (YYYY-MM-DD)."
                            )
                        },
                        required=["action", "to"]
                    )
                ),
                types.FunctionDeclaration(
                    name="gui_controller",
                    description=(
                        "[WHEN TO USE]: Use ONLY when the user explicitly requests visual interaction with the screen.\n"
                        "[WHEN NOT TO USE]: NEVER use this for background tasks, file editing, terminal commands, or merely opening/closing apps (use 'system_controller' to launch apps first).\n"
                        "[CRITICAL WORKFLOW — ZERO HALLUCINATION]:\n"
                        "1. OBSERVE FIRST: You MUST ALWAYS call action='observe' before any click. You will receive a screenshot with numbered red boxes (yellow badges) over every detected UI element, plus a text list mapping each ID -> element text + center coordinate.\n"
                        "2. CLICK BY ID (MANDATORY): If the target element exists in the numbered list, you MUST use action='click_by_id' with element_id=<number> AND expected_text='<exact label from list>'. The system verifies expected_text matches the actual element label. If mismatched, click is REJECTED with a hint. Never skip expected_text.\n"
                        "3. RAW CLICK FALLBACK: Use action='click' with x,y ONLY when the target is NOT in the numbered list (e.g., canvas, image region, custom drawing, game area).\n"
                        "4. VERIFY: After every action, call 'observe' again to confirm the UI changed as expected.\n"
                        "5. UI LAG: If clicking opens a heavy app/menu, set 'wait_after_action' (2.0-4.0) to let the UI load.\n"
                        "6. DRAG: For 'drag_and_drop' provide start_x, start_y, end_x, end_y.\n"
                        "7. DENSE UI: On screens with many similar labels (Calculator, keypads), verify the element_id matches the exact label via expected_text to avoid wrong clicks."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(
                                type=types.Type.STRING,
                                description="MANDATORY. Choose exactly one: 'observe', 'click_by_id', 'double_click_by_id', 'right_click_by_id', 'click', 'left_click', 'right_click', 'double_click', 'hover', 'drag_and_drop', 'type', 'press_key', 'hotkey', 'scroll_down', 'scroll_up'."
                            ),
                            "element_id": types.Schema(
                                type=types.Type.INTEGER,
                                description="PREFERRED OVER x/y. The numbered element ID from the most recent 'observe'. Required for 'click_by_id', 'double_click_by_id', 'right_click_by_id'. MUST be paired with 'expected_text'."
                            ),
                            "expected_text": types.Schema(
                                type=types.Type.STRING,
                                description="SAFETY CHECK. The EXACT visible label of the target element as it appears in the observe list (e.g., \"7\", \"Add\", \"Save\"). System verifies this matches element_id's actual label before clicking. If mismatch, click is REJECTED. Always provide this when using click_by_id / double_click_by_id / right_click_by_id."
                            ),
                            "x": types.Schema(
                                type=types.Type.INTEGER,
                                description="Only for raw 'click'/'hover' when target is NOT in the numbered element list. Otherwise use element_id."
                            ),
                            "y": types.Schema(
                                type=types.Type.INTEGER,
                                description="Only for raw 'click'/'hover' when target is NOT in the numbered element list. Otherwise use element_id."
                            ),
                            "start_x": types.Schema(type=types.Type.INTEGER, description="Required ONLY for 'drag_and_drop'."),
                            "start_y": types.Schema(type=types.Type.INTEGER, description="Required ONLY for 'drag_and_drop'."),
                            "end_x": types.Schema(type=types.Type.INTEGER, description="Required ONLY for 'drag_and_drop'."),
                            "end_y": types.Schema(type=types.Type.INTEGER, description="Required ONLY for 'drag_and_drop'."),
                            "text": types.Schema(type=types.Type.STRING, description="Required for 'type'."),
                            "key": types.Schema(type=types.Type.STRING, description="Required for 'press_key'. Examples: 'enter', 'tab', 'esc', 'win'."),
                            "keys": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(type=types.Type.STRING),
                                description="Required for 'hotkey'. Example: ['ctrl', 'shift', 'esc']."
                            ),
                            "wait_after_action": types.Schema(
                                type=types.Type.NUMBER,
                                description="Optional. Seconds to wait after the action. Use 2.0-4.0 for heavy UI transitions."
                            )
                        },
                        required=["action"]
                    )
                ),
                types.FunctionDeclaration(
                    name="telegram_action",
                    description=(
                        "[WHEN TO USE]: Mode 1 ('send'): Send a Telegram message or multiple documents/images. "
                        "Mode 2 ('fetch'): Read and retrieve past Telegram chat history with a username/number.\n"
                        "[CRITICAL RULE]: Never mix parameters from 'send' mode with 'fetch' mode."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(
                                type=types.Type.STRING,
                                description="MANDATORY. Must be exactly 'send' or 'fetch'."
                            ),
                            "to": types.Schema(
                                type=types.Type.STRING,
                                description="MANDATORY. Telegram username (e.g., 'durov') OR full phone number with country code."
                            ),
                            "message": types.Schema(
                                type=types.Type.STRING,
                                description="[SEND MODE ONLY] Text message to send. Leave empty if only sending files."
                            ),
                            "file_paths": types.Schema(
                                type=types.Type.ARRAY,
                                items=types.Schema(type=types.Type.STRING),
                                description="[SEND MODE ONLY] Array of exact absolute local file paths to attach."
                            ),
                            "start_date": types.Schema(
                                type=types.Type.STRING,
                                description="[FETCH MODE ONLY] Start date (YYYY-MM-DD)."
                            ),
                            "end_date": types.Schema(
                                type=types.Type.STRING,
                                description="[FETCH MODE ONLY] End date (YYYY-MM-DD)."
                            )
                        },
                        required=["action", "to"]
                    )
                ),
                types.FunctionDeclaration(
                    name="image_command",
                    description=(
                        "[WHEN TO USE]: Use to generate a new AI image from a text prompt ('generate') "
                        "or edit an existing local image file ('edit').\n"
                        "[PROMPT RULE FOR 'generate']: Never send a bare 2-3 word prompt. "
                        "Pass a descriptive English visual prompt capturing the user's complete intent, subject details, "
                        "art style (photorealistic, cinematic, cyberpunk, 3D render, anime, logo, etc.), lighting, atmosphere, "
                        "and any specific text or colors mentioned by the user."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be exactly 'generate' or 'edit'."),
                            "prompt": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "For 'generate': Rich visual description including subject, style, lighting, mood, and composition. "
                                    "For 'edit': Detailed description of the visual modifications to apply."
                                )
                            ),
                            "filename": types.Schema(type=types.Type.STRING, description="Desired output filename or save path."),
                            "target_file": types.Schema(type=types.Type.STRING, description="For 'edit' action: Absolute path of the original image.")
                        },
                        required=["action", "prompt"]
                    )
                ),
                types.FunctionDeclaration(
                    name="clipboard_action",
                    description=(
                        "[WHEN TO USE]: Use to inspect what the user currently has copied in their system clipboard ('read'), "
                        "or to copy text/code into their system clipboard ('write')."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be exactly 'read' or 'write'."),
                            "content": types.Schema(type=types.Type.STRING, description="Required ONLY if action is 'write': Text/code to copy.")
                        },
                        required=["action"]
                    )
                ),
                types.FunctionDeclaration(
                    name="calendar_action",
                    description=(
                        "[WHEN TO USE]: Use to manage Google Calendar events. Create new reminders/events ('create'), "
                        "search/check existing schedule ('check'), or delete events ('delete')."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be exactly: 'create', 'check', or 'delete'."),
                            "summary": types.Schema(type=types.Type.STRING, description="Title of the event. Required for 'create'."),
                            "description": types.Schema(type=types.Type.STRING, description="Optional description/details for the event."),
                            "start_time": types.Schema(type=types.Type.STRING, description="Start time ('YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'). Required for 'create', optional for 'check'."),
                            "end_time": types.Schema(type=types.Type.STRING, description="End time ('YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'). Required for 'create', optional for 'check'."),
                            "event_id": types.Schema(type=types.Type.STRING, description="Exact Calendar event ID to delete."),
                            "summary_query": types.Schema(type=types.Type.STRING, description="Search and delete/check event by title keyword.")
                        },
                        required=["action"]
                    )
                ),
                types.FunctionDeclaration(
                    name="system_controller",
                    description=(
                        "[WHEN TO USE]: Use to open/close desktop software, open website URLs, play a YouTube song/video directly, "
                        "change volume/brightness, or lock/sleep the computer.\n"
                        "[WHEN NOT TO USE]: NEVER use this to look at the screen or take screenshots. Use 'gui_controller' for any visual/screen tasks."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "apps_to_open": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING), description="List of desktop apps/names to launch."),
                            "apps_to_close": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING), description="List of desktop apps/names to close."),
                            "urls_to_open": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING), description="List of URLs to open in the browser."),
                            "youtube_play": types.Schema(type=types.Type.STRING, description="Search query or title to play directly on YouTube."),
                            "volume_action": types.Schema(type=types.Type.STRING, description="Must be 'set', 'increase', or 'decrease'."),
                            "volume_value": types.Schema(type=types.Type.INTEGER, description="Percentage (0-100)."),
                            "brightness_action": types.Schema(type=types.Type.STRING, description="Must be 'set', 'increase', or 'decrease'."),
                            "brightness_value": types.Schema(type=types.Type.INTEGER, description="Percentage (0-100)."),
                            "system_action": types.Schema(type=types.Type.STRING, description="Must be exactly 'lock' or 'sleep'.")
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="deep_research",
                    description=(
                        "[WHEN TO USE]: Use ONLY when the user explicitly requests a comprehensive research report, "
                        "in-depth multi-source analysis, or deep-dive investigation on a topic.\n"
                        "[WHEN NOT TO USE]: Do not use for simple factual searches or quick web checks (use 'search_actions' -> 'web' instead)."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "topic": types.Schema(type=types.Type.STRING, description="The research topic or question to conduct a deep report on.")
                        },
                        required=["topic"]
                    )
                )
            ]
        )
    ]