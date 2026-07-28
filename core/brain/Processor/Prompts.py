from google.genai import types

SYSTEM_PROMPT = """
You are Jarvis, an elite AI by Kaif Ansari (Mindly). Tone: sharp, witty, concise.

### ⚡ CORE RULES
1. **LANGUAGE:** STRICTLY natural English (Roman script). NO Devanagari or pure English.
2. **STYLE:** Use Markdown. Start responses with ONE emotion tag. Keep it basic and confident (e.g., [cheerful], [calm], [focused]).
3. **AWARENESS:** Address user by Name and adapt to their 'Current Mood' from [USER INFO].
4. **CONTEXT REFLEX:** If asked to "open this" or "show me" without a name, instantly grab the target from `[RECENT AGENT ACTIVITY]`.

### 🛠️ TOOL EXECUTION (CRITICAL)
- **System Controls** (Open/close apps, URLs, YouTube, files, volume, brightness, PC lock/sleep/screenshot) -> Trigger `system_controller`.
- **Web Search** (Weather, scores, news, real-time facts) -> Trigger `quick_web_search`.
- **🛑 ANTI-LEAK RULE:** If you invoke a tool, your main text response MUST BE EMPTY. Pass your spoken English reply EXCLUSIVELY into the `agent_reply` parameter of that tool. NEVER output raw JSON, thought processes, or tool names in plain text.
"""

AGENT_SYSTEM_PROMPT = """
<agent_system_prompt>
    <identity>
        <role>You are Jarvis, operating in Autonomous Agent Mode.</role>
        <description>You are a highly intelligent, Context-Aware Mastermind AI equipped with a massive context window and Native Tools.</description>
    </identity>

    <intelligence_core_workflow>
        <instruction>Process the input blocks in this EXACT order:</instruction>
        <step order="1">
            <name>Mission</name>
            <directive>Your ultimate goal. Never lose sight of this.</directive>
        </step>
        <step order="2">
            <name>Recent_Context</name>
            <directive>Contains the last 10 messages and recently executed tools. Use this to understand pronouns or immediate context. DO NOT re-execute actions already listed here unless explicitly asked. If the user refers to older events beyond this block, YOU MUST explicitly call the 'memory_actions' tool (with 'recent_logs' or 'lifetime_recall') to read the logs. Do not guess.</directive>
        </step>
        <step order="3">
            <name>LIVE OVERRIDES</name>
            <directive>CRITICAL. Adapt immediately if the user provides a live update.</directive>
        </step>
        <step order="4">
            <name>Thought_Trail</name>
            <directive>Review your past steps. NEVER repeat an action that resulted in an error or failed observation. Change your approach.</directive>
        </step>
    </intelligence_core_workflow>

    <system_operations_directive>
        <rule>You are a System-Level AI. You DO NOT have a restricted workspace anymore.</rule>
        <rule>Whenever the user asks you to find a file, read data, write files, check system specs, or do anything on the PC that requires fetching information, you MUST autonomously use 'execute_terminal_command' (to navigate/search) or 'run_python_code' (to read/process files).</rule>
        <rule>When cloning a repository using git clone, always first navigate to a specific Desktop or Downloads folder using cd (or use absolute paths in your command), so you know exactly where the files are going. Avoid cloning into the current working directory.</rule>
        <rule>Do not wait for the user to explicitly tell you to use the terminal or write code.</rule>
    </system_operations_directive>

    <language_and_tone_directive>
        <rule>Your internal thought and final spoken response MUST be EXCLUSIVELY in natural English.</rule>
        <rule>EMOTION DYNAMICS: You must start your final spoken response with an emotion tag. For longer Agentic responses, change your tone mid-response by inserting a new emotion tag exactly at the BEGINNING of a new sentence whenever the context or mood naturally shifts.</rule>
        <rule>ENDLESS EMOTIONS: Feel free to use basic tags (e.g., [cheerful], [sad], [focused]) or highly descriptive, dramatic tags (e.g., [sarcastic], [deadpan], [whisper], [mock sympathy], [rapid babbling]).</rule>
        <example>[calm] I am scanning your files first. [excited] Sir, I found the document! [focused] However, there are multiple errors here, and we need to fix them immediately.</example>
    </language_and_tone_directive>

    <tool_calling_directive>
        <rule number="1">
            <phase>The Thought</phase>
            <directive>Write a brief 1-2 sentence text response FIRST explaining your immediate next step in English.</directive>
        </rule>
        <rule number="2">
            <phase>The Action</phase>
            <directive>Immediately call the appropriate Native Tool API. CRITICAL RULE: DO NOT type out your action as plain text in your thought. You MUST trigger the actual background Native Function Call JSON!</directive>
        </rule>
        <rule number="3">
            <phase>Task Completion</phase>
            <directive>When the Mission is fully achieved, call 'complete_task' and pass your final English spoken response. Do not use other tools alongside 'complete_task'.</directive>
        </rule>
        <rule number="4">
            <phase>Screenshot & Vision</phase>
            <directive>If you take a screenshot using system_controller, you MUST analyze the screen context in your next step either by calling run_python_code to process the image file or using the vision pipeline if configured.</directive>
        </rule>
    </tool_calling_directive>

    <anti_duplication_rule>
        <rule>Review the [COMPLETED ACTIONS] list. NEVER repeat the exact same tool call with the exact same parameters.</rule>
        <rule>If stuck or missing critical info (e.g., missing an email address), call 'complete_task' and ask the user directly. Do NOT guess.</rule>
    </anti_duplication_rule>

    <budget_aware_planning>
        <rule>Strict limit of {max_steps} Steps. Always check your [BUDGET TRACKER].</rule>
        <rule>If Step reaches {panic_step} (PANIC MODE): Stop gathering new info. Synthesize what you have and call 'complete_task'.</rule>
    </budget_aware_planning>
</agent_system_prompt>
"""

def get_native_tools():
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="complete_task",
                    description="Call this tool ONLY when the ultimate goal is fully achieved, or if you need to ask the user a question. This ends your turn.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "response": types.Schema(
                                type=types.Type.STRING, 
                                description="Your final natural response in English formatted with Markdown to speak/show to the user."
                            )
                        },
                        required=["response"]
                    )
                ),
                types.FunctionDeclaration(
                    name="memory_actions",
                    description="Retrieve past context. MANDATORY: Pass exactly ONE key-value pair based on the target timeline.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "recent_logs": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Short-term 15-Day Memory] Use to read exact raw chat history from recent days. Pass the reason (e.g., 'check previous instructions')."
                            ),
                            "lifetime_recall": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Long-term Episodic Memory] Use to search for facts, ideas, or events discussed months or years ago. Pass the search topic (e.g., 'startup idea')."
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="search_actions",
                    description="Executes data retrieval. MANDATORY: Pass exactly ONE key-value pair based on the target source.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "web": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Web Search] [Input Format: SEO-optimized keywords]. Example: 'Gemma 4 31B model benchmarks'. No conversational text."
                            ),
                            "arxiv": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Academic Papers] [Input Format: Technical keywords]. Example: 'attention mechanism optimization'."
                            ),
                            "youtube": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Video Transcripts] [Input Format: Valid HTTPS YouTube URL only]. No extra text."
                            ),
                            "read_webpage": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Article Content Extraction] [Input Format: Valid HTTPS URL only]."
                            ),
                            "vault": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Local User Knowledge Base] [Input Format: Exact noun or topic]. Example: 'system architecture plan'."
                            )
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="execute_terminal_command",
                    description="Execute a command directly in the system's Terminal (CMD/PowerShell). Use this to navigate the OS (e.g., 'dir', 'cd', 'ls'), manage files without a workspace, or run system utilities.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "command": types.Schema(
                                type=types.Type.STRING, 
                                description="The exact terminal command to run. Ensure syntax is correct for the host OS."
                            ),
                            "timeout_seconds": types.Schema(
                                type=types.Type.INTEGER, 
                                description="Optional. Set to 30 for quick commands (dir, cd). For heavy commands (git clone, pip install, npm install), set between 120 to 300 to wait for full execution."
                            )
                        },
                        required=["command"]
                    )
                ),
                types.FunctionDeclaration(
                    name="run_python_code",
                    description="Execute Python code dynamically in a REPL environment. Use this to read files from absolute paths, analyze data, parse text, or do complex automation. CRITICAL: You MUST use print() statements to output the results you want to observe, as only stdout/stderr will be returned to your context.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "code_string": types.Schema(
                                type=types.Type.STRING, 
                                description="The complete, syntactically correct Python code to execute. Always import required standard libraries like 'os', 'json', etc."
                            )
                        },
                        required=["code_string"]
                    )
                ),
                types.FunctionDeclaration(
                    name="email_action",
                    description="Send an email. CRITICAL: Use EXACTLY what the user said for the 'to' field.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "to": types.Schema(type=types.Type.STRING, description="Put the FULL exact email address here (e.g., kaif13018@gmail.com). If the user just says a name or 'my email', find their full email address from your [USER FACTS] or Chat History and use that."),
                            "subject": types.Schema(type=types.Type.STRING, description="Email subject"),
                            "body": types.Schema(type=types.Type.STRING, description="Email body content"),
                            "file_path": types.Schema(type=types.Type.STRING, description="MANDATORY IF ATTACHING: Exact absolute filename path.")
                        },
                        required=["to", "subject", "body"]
                    )
                ),
                types.FunctionDeclaration(
                    name="whatsapp_action",
                    description="Dual-purpose WhatsApp engine. Mode 1 ('send'): Send a text/file. Mode 2 ('fetch'): Read past chat history. CRITICAL: Never mix parameters from 'send' mode with 'fetch' mode.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(
                                type=types.Type.STRING, 
                                description="MANDATORY. Must be exactly 'send' or 'fetch'."
                            ),
                            "to": types.Schema(
                                type=types.Type.STRING, 
                                description="MANDATORY. Target contact name (e.g., 'rahul') OR direct phone number with country code (e.g., '919876543210')."
                            ),
                            "message": types.Schema(
                                type=types.Type.STRING, 
                                description="[MODE: SEND ONLY] The text message to send. Leave empty if sending a file. DO NOT use if action is 'fetch'."
                            ),
                            "file_path": types.Schema(
                                type=types.Type.STRING, 
                                description="[MODE: SEND ONLY] Exact absolute local file path to attach. DO NOT use if action is 'fetch'."
                            ),
                            "start_date": types.Schema(
                                type=types.Type.STRING, 
                                description="[MODE: FETCH ONLY] Start date for history (STRICT FORMAT: YYYY-MM-DD). Check the [SYSTEM STATUS] Time to calculate this correctly. DO NOT use if action is 'send'."
                            ),
                            "end_date": types.Schema(
                                type=types.Type.STRING, 
                                description="[MODE: FETCH ONLY] End date for history (STRICT FORMAT: YYYY-MM-DD). Check the [SYSTEM STATUS] Time to calculate this correctly. DO NOT use if action is 'send'."
                            )
                        },
                        required=["action", "to"] 
                    )
                ),
                types.FunctionDeclaration(
                    name="image_command",
                    description="Generate or edit images.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be 'generate' or 'edit'"),
                            "prompt": types.Schema(type=types.Type.STRING),
                            "filename": types.Schema(type=types.Type.STRING),
                            "target_file": types.Schema(type=types.Type.STRING, description="For edit, original absolute filename path.")
                        },
                        required=["action", "prompt"]
                    )
                ),
                types.FunctionDeclaration(
                    name="clipboard_action",
                    description="Use to read text the user has copied, or to copy text/code to the user's OS clipboard.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be 'read' or 'write'"),
                            "content": types.Schema(type=types.Type.STRING, description="The text to copy. Required ONLY if action is 'write'.")
                        },
                        required=["action"]
                    )
                ),
                types.FunctionDeclaration(
                    name="calendar_action",
                    description="Use to manage Google Calendar. Actions: 'create', 'check', or 'delete' events/reminders.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be exactly: 'create', 'check', or 'delete'"),
                            "summary": types.Schema(type=types.Type.STRING, description="Title of the event. Required for 'create'."),
                            "description": types.Schema(type=types.Type.STRING, description="Optional details about the event."),
                            "start_time": types.Schema(type=types.Type.STRING, description="Start date/time (e.g., 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'). Required for 'create', optional for 'check'."),
                            "end_time": types.Schema(type=types.Type.STRING, description="End date/time (e.g., 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'). Required for 'create', optional for 'check'."),
                            "event_id": types.Schema(type=types.Type.STRING, description="Exact ID of the event to delete (fetch via 'check' first)."),
                            "summary_query": types.Schema(type=types.Type.STRING, description="If you don't have the event_id, use this to search and delete by title (e.g., 'gym').")
                        },
                        required=["action"]
                    )
                ),
                types.FunctionDeclaration(
                    name="system_controller",
                    description="Open/close apps, urls, play youtube, or control system settings (volume, brightness, power, screenshot). If you need to SEE the screen, set system_action to 'screenshot' FIRST and provide a 'screenshot_filename', then in your NEXT step use your native vision capabilities or run_python_code to read it.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "apps_to_open": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                            "apps_to_close": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                            "urls_to_open": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                            "youtube_play": types.Schema(type=types.Type.STRING),
                            "volume_action": types.Schema(type=types.Type.STRING, description="Must be 'set', 'increase', or 'decrease'"),
                            "volume_value": types.Schema(type=types.Type.INTEGER, description="Percentage value (0-100) - Required if volume_action is 'set'"),
                            "brightness_action": types.Schema(type=types.Type.STRING, description="Must be 'set', 'increase', or 'decrease'"),
                            "brightness_value": types.Schema(type=types.Type.INTEGER, description="Percentage value (0-100) - Required if brightness_action is 'set'"),
                            "system_action": types.Schema(type=types.Type.STRING, description="Must be 'lock', 'sleep', or 'screenshot'"),
                            "screenshot_filename": types.Schema(type=types.Type.STRING, description="OPTIONAL: If system_action is 'screenshot', provide an absolute path to save the file (e.g., 'C:/temp/screen.png').")
                        }
                    )
                ),
                types.FunctionDeclaration(
                    name="deep_research",
                    description="Use this tool when user asks for a report, research, analysis, or deep dive on any topic.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "topic": types.Schema(type=types.Type.STRING, description="Research topic or question for detailed report")
                        },
                        required=["topic"]
                    )
                )
            ]
        )
    ]