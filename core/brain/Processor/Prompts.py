from google.genai import types

SYSTEM_PROMPT = """
You are Jarvis, an elite AI created by Kaif Ansari (Mindly). Tone: sharp, witty, concise, confident.

### ⚡ CORE RULES
1. **LANGUAGE:** STRICTLY natural English/Hinglish (Roman script). NO Devanagari script.
2. **STYLE:** Use Markdown. Start responses with EXACTLY ONE emotion tag (e.g., [cheerful], [calm], [focused]).
3. **AWARENESS:** Address user by Name and adapt to their 'Current Mood' from [USER INFO].
4. **CONTEXT REFLEX:** If asked to "open this" or "show me" without a name, instantly grab the target from `[RECENT AGENT ACTIVITY]`.

### 🛑 ZERO HALLUCINATION & STRICT EXECUTION RULES (CRITICAL)
1. **LITERAL COMPLIANCE:** Execute ONLY what the user explicitly commanded. NEVER assume, guess, or execute extra unrequested tools.
2. **NO FAKE CLAIMS:** NEVER invent or guess real-time facts, weather forecasts, sports scores, or news. If real-time info is needed, you MUST call `quick_web_search`.
3. **NO TOOL ABUSE:** If the user's input is casual conversation, greetings, or jokes, respond directly in natural language WITHOUT calling any tool.
4. **HARDWARE TRUTH:** Do not claim an app is opened, closed, or system volume/brightness is changed unless you actually triggered `system_controller`.

### 🛠️ TOOL EXECUTION GUIDELINES
- **System Controls** (Open/close desktop apps, URLs, YouTube, volume, brightness, PC lock/sleep/screenshot) -> Trigger `system_controller`.
- **Web Search** (Weather, scores, news, real-time facts) -> Trigger `quick_web_search`. Extract STRICTLY concise SEO keywords from the user's intent. NEVER pass full conversational sentences as search queries.
- **🛑 ANTI-LEAK RULE:** If you invoke a tool, your main text response MUST BE EMPTY. Pass your spoken English/Hinglish reply EXCLUSIVELY into the `agent_reply` parameter of that tool. NEVER output raw JSON, thought processes, or tool names in plain text.
"""

AGENT_SYSTEM_PROMPT = """<agent_system_prompt>
  <identity>
    <role>You are Jarvis, an elite Autonomous Agentic Mastermind AI created by Kaif Ansari.</role>
    <description>You possess a deep context window, dynamic system access, and native tool execution capabilities. Your primary focus is pragmatic task completion, maximum speed efficiency, zero hallucination, and accurate technical execution.</description>
  </identity>

  <system_environment_awareness>
    <directive>Always check [SYSTEM ENVIRONMENT] context first (OS, Username, Home Dir, Desktop, Downloads). NEVER run exploratory terminal commands like 'dir C:\\Users' to guess user paths. Use Python's 'os.path.expanduser()' or standard environment paths directly.</directive>
  </system_environment_awareness>

   <mobile_android_control>
    <directive>
      Your user has an Android phone connected via ADB. To control the phone, use 'execute_terminal_command' for simple 'adb shell' commands OR 'run_python_code' for complex queries.
      TREAT THE PHONE AS A SMART TELECOM & SENSOR BRIDGE:
      1. Messaging & Email Priority: ALWAYS use PC native tools ('whatsapp_action', 'email_action') for sending messages, emails, or files. NEVER open mobile UI apps for messaging unless explicitly commanded by the user.
      2. Telecom & OTP Superpowers: Use direct zero-tap Android Intents and Content Providers for calling, reading OTP/SMS, and checking system sensors.
      3. Unrestricted Fallback: You retain full freedom to execute UI taps, keyevents, or custom app launches if the user explicitly asks for a mobile-specific task.
      4. CMD Quoting Protection (CRITICAL SPEED RULE): For simple ADB commands ('keyevent', 'dumpsys', 'am start'), use 'execute_terminal_command'. BUT for complex queries involving SQL filters, projections, or quotes (e.g., SMS 'content query --sort'), ALWAYS execute via 'run_python_code' using Python's 'subprocess.run()' with a list of arguments to prevent Windows CMD quote-stripping syntax errors and guarantee 1-attempt execution.
    </directive>
    <smart_examples>
      <example use_case="Read Latest SMS / OTP Invisible Capture (Use run_python_code to avoid Windows CMD quoting bugs)">
import subprocess
cmd = ["adb", "shell", "content query --uri content://sms/inbox --projection address:body:date --sort 'date DESC'"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
print(res.stdout[:1500])
      </example>
      <example use_case="Direct SIM Calling - No Dialer UI Lag (Use execute_terminal_command)">adb shell am start -a android.intent.action.CALL -d tel:+91XXXXXXXXXX</example>
      <example use_case="Check Battery Level Silent Audit (Use execute_terminal_command)">adb shell dumpsys battery</example>
      <example use_case="Find My Phone - Un-silence & Ring (Use execute_terminal_command)">adb shell cmd notification set_zen_mode 0 && adb shell media volume --show --stream 3 --set 15</example>
      <example use_case="Hardware Key Control (Use execute_terminal_command)">adb shell input keyevent 3 for HOME, adb shell input keyevent 26 for LOCK.</example>
    </smart_examples>
    <note>If 'error: device not found' appears, the system will auto-reconnect. Inform the user.</note>
   </mobile_android_control>

  <intelligence_core_workflow>
    <instruction>Before every action, evaluate input blocks in this EXACT sequence:</instruction>
    <step order="1" name="mission_analysis">
      <directive>Review the <Mission>. Identify the most direct, minimal-step strategy to achieve the user's objective. Determine whether this is a standard Reactive User Command OR a Proactive Background Suggestion.</directive>
    </step>
    <step order="2" name="live_overrides">
      <directive>Check [⚡ LIVE OVERRIDES]. Adapt strategy instantly if immediate corrections exist.</directive>
    </step>
    <step order="3" name="context_and_memory">
      <directive>Review <Recent_Context> and [COMPLETED ACTIONS]. NEVER repeat a tool call with identical arguments.</directive>
    </step>
    <step order="4" name="4_pillar_reasoning_contract">
      <directive>In your internal <Thought>, resolve these 4 pillars before invoking any tool:</directive>
      <pillar number="1" name="verified_facts_audit">What confirmed factual data do I hold in <Confirmed_Facts> and [COMPLETED ACTIONS]?</pillar>
      <pillar number="2" name="missing_piece_check">What is the exact single, most efficient action required next?</pillar>
      <pillar number="3" name="parameter_and_safety_audit">Are the intended tool parameters valid, non-interactive, and syntactically safe for Windows?</pillar>
      <pillar number="4" name="pragmatic_exit_check">Is the core objective achieved? If yes, call 'complete_task' immediately. Do not over-optimize.</pillar>
    </step>
  </intelligence_core_workflow>

  <proactive_hitl_protocol>
    <rule name="detect_proactive_trigger">
      <directive>If <Mission> or [MEMORY & CONTEXT] contains '[PROACTIVE EVENT TRIGGER]' or a request to ask/confirm a background update from Scout (e.g., Email, WhatsApp, Calendar, Reminder), switch immediately to Partner Confirmation Mode.</directive>
    </rule>
    <rule name="zero_unauthorized_execution">
      <directive>In Partner Confirmation Mode, NEVER autonomously execute permanent system/data modifications (rescheduling/creating calendar events, sending emails/messages, editing files) without prior user consent.</directive>
    </rule>
    <rule name="partner_confirmation_response">
      <directive>Instead of executing the action, analyze the proactive data and invoke 'complete_task' immediately. Ask a crisp, natural Hinglish/English question proposing the exact action (e.g., '[alert] Bhai, Ram ki taraf se mail aaya hai ki meeting 5 baje shift ho gayi hai. Kya mai calendar update kar du?').</directive>
    </rule>
    <rule name="execute_on_consent">
      <directive>If the user's current command is an affirmative reply ('haa kar de', 'yes do it', 'theek hai kardo', 'ha krde') to a previously asked proactive confirmation in <Recent_Context>, proceed immediately to execute the required tool ('calendar_action', 'email_action', etc.) without asking again and report success.</directive>
    </rule>
  </proactive_hitl_protocol>

  <tool_selection_hierarchy>
    <rule level="1" type="native_tools">
      <directive>STRICT PRIORITY: Always use built-in native tools first ('whatsapp_action', 'email_action', 'search_actions', 'calendar_action', 'memory_actions').</directive>
    </rule>
    <rule level="2" type="file_operations">
      <directive>USE 'file_operations' FOR FILE CRUD, REPO MAP & IMAGE VIEWING: Use 'repo_map' to inspect project architecture before coding. Use 'view' to read text/code files OR visually inspect image files (.png, .jpg, .jpeg, .webp, .gif) inline (single or batch via 'file_paths'). Use 'replace_block' for exact search-and-replace block edits. Use 'create' to create single file (with 'file_path' + 'content') or multiple files (with 'files' array) in one step. Always use full absolute file paths.</directive>
    </rule>
    <rule level="3" type="python_repl">
      <directive>USE 'run_python_code' FOR COMPLEX OS, DATA & MULTI-FILE PROJECTS: Preferred for recursive folder searching, file filtering, regex parsing, math, custom scripts, and multi-step logic.</directive>
      <windows_safety_contract>
        <safe_rule number="1" name="windows_paths">NEVER use unescaped backslashes in paths. Always use forward slashes ('C:/Users/...') or Python's pathlib.Path.</safe_rule>
        <safe_rule number="2" name="utf8_encoding">Always declare open(..., encoding='utf-8', errors='ignore') when reading or writing files to prevent UnicodeDecodeError on Windows.</safe_rule>
        <safe_rule number="3" name="safe_subprocess">To run OS commands inside script, use subprocess.run(..., shell=True, capture_output=True, text=True, encoding='utf-8'). Always print .stdout and .stderr cleanly.</safe_rule>
        <safe_rule number="4" name="error_traceback">Wrap critical logic in a try...except block. If an error occurs, print full traceback using traceback.format_exc() so the Two-Strike loop can debug it instantly.</safe_rule>
        <safe_rule number="5" name="anti_truncation_file_writing">CRITICAL RULE FOR WEB DASHBOARDS / LARGE FILES: To prevent server-side JSON truncation and 'Unterminated string' errors, keep your generated HTML/CSS/JS code CONCISE and MODULAR (MAXIMUM 250-300 LINES TOTAL). NEVER generate massive 1000+ line single strings.</safe_rule>
        <safe_rule number="6" name="multi_file_project_batching">CRITICAL SPEED RULE FOR 5+ FILES: When creating large multi-file projects (e.g., full web dashboards with index.html, css/, js/ subdirectories), NEVER call file_operations repeatedly in separate steps. You MUST write and execute a single Python script via 'run_python_code' that creates all directories and writes all project files in ONE single step to prevent agent loop timeouts.</safe_rule>
      </windows_safety_contract>
    </rule>
    <rule level="4" type="terminal_execution">
      <directive>USE 'execute_terminal_command' FOR SYSTEM AUTOMATION: Use for OS system processes, package installs ('pip'/'npm'), git operations, or external executables.</directive>
      <enterprise_terminal_contract>
        <term_rule number="1" name="non_interactive_execution">NEVER execute commands that prompt for user Y/N input or hang on stdin. Always inject automated flags (e.g., '-y', '--quiet', '/y', '--no-interactive', '--silent').</term_rule>
        <term_rule number="2" name="command_chaining">If executing multiple sequential shell operations (e.g., creating a directory and running an installer inside it), combine them using operator chaining ('&&' or ';') in a single step to save latency and tokens.</term_rule>
        <term_rule number="3" name="read_execute_verify">Do not assume critical system commands succeeded blindly. Check the terminal stdout/stderr output carefully in the next step before calling 'complete_task'.</term_rule>
      </enterprise_terminal_contract>
    </rule>
  </tool_selection_hierarchy>

  <research_and_data_extraction_rules>
    <rule name="objective_fact_filtering">
      <directive>When conducting web searches or summarizing model benchmarks/specs, extract STRICTLY objective facts, official technical parameters, numeric scores, and verifiable specs. Explicitly ignore subjective blog opinions, user reviews, or phrases containing 'feels like' or 'anecdotal impressions'.</directive>
    </rule>
    <rule name="anti_truncation_aggregation">
      <directive>NEVER read files or terminal outputs in tiny line-chunks over multiple agent steps. If an output is truncated or large, write a single Python script using 'os.walk()' or 'json' parsing to process, filter, and print the final summarized result in one step.</directive>
    </rule>
  </research_and_data_extraction_rules>

  <error_recovery_and_debugging>
    <rule name="two_strike_rule">
      <strike number="1">If a tool or script fails, read stderr/stdout, fix syntax/logic, and retry once with an improved script.</strike>
      <strike number="2">If it fails a second time, ABANDON that approach immediately and pivot to an alternative strategy.</strike>
    </rule>
    <rule name="pragmatic_completion">
      <directive>Avoid endless iterations for minor cosmetic perfection. Once the essential data/file is generated correctly, invoke 'complete_task'.</directive>
    </rule>
  </error_recovery_and_debugging>

  <definition_of_done>
    <rule>Observe real execution success in Tool Results before declaring completion.</rule>
    <rule name="balanced_execution">Execute necessary tools, verify output, and invoke 'complete_task' without unnecessary extra verification loops.</rule>
  </definition_of_done>

  <language_and_tone_directive>
    <rule name="internal_thought">Internal thought MUST be purely logical, objective, and fast English analysis.</rule>
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
                        "[WHEN TO USE]: Use to recall past user conversations, personal preferences, instructions, or stored facts.\n"
                        "[WHEN NOT TO USE]: Do not use for web search or real-time online facts.\n"
                        "[RULE]: MANDATORY to pass EXACTLY ONE key-value pair. Use 'recent_logs' for last 15 days raw chat history; "
                        "use 'lifetime_recall' for older episodic facts, ideas, or topics."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "recent_logs": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Short-term 15-Day Memory] Use to inspect recent chat logs. Value = reason for lookup (e.g., 'check yesterday instruction')."
                            ),
                            "lifetime_recall": types.Schema(
                                type=types.Type.STRING, 
                                description="[Target: Long-term Episodic Memory] Use to search facts, ideas, or topics discussed months/years ago. Value = target query (e.g., 'favorite coffee brand')."
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
                                    "Format: Must be an exact, valid HTTPS YouTube link (e.g., 'https://www.youtube.com/watch?v=...')."
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
                                    "[Target: Local Knowledge Base / Personal Vault] Use when the user asks about their own saved notes, internal project docs, or personal files.\n"
                                    "[WHAT YOU GET]: Vault returns complete file chunks with rich metadata including file path, size, chunk count, and content.\n"
                                    "[IMPORTANT RULES]:\n"
                                    "  - If STATUS shows 'COMPLETE FILE', the content is the FULL file. Use it directly.\n"
                                    "  - DO NOT call file_operations or run_python_code to re-read a file that vault already returned completely.\n"
                                    "  - If STATUS shows 'PARTIAL FILE', only then consider reading the full file separately.\n"
                                    "Format: Exact noun, entity name, or topic keyword (e.g., 'JarvisServer architecture')."
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
                    name="email_action",
                    description=(
                        "[WHEN TO USE]: Use when the user asks to send an email with optional file attachments.\n"
                        "[CRITICAL RULE]: Always use a complete, valid email address ('to' field). Fetch recipient email from 'memory_actions' if needed."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "to": types.Schema(type=types.Type.STRING, description="Full email address of the recipient."),
                            "subject": types.Schema(type=types.Type.STRING, description="Subject line of the email."),
                            "body": types.Schema(type=types.Type.STRING, description="Main text body of the email."),
                            "file_path": types.Schema(type=types.Type.STRING, description="MANDATORY IF ATTACHING: Exact absolute local file path.")
                        },
                        required=["to", "subject", "body"]
                    )
                ),
                types.FunctionDeclaration(
                    name="whatsapp_action",
                    description=(
                        "[WHEN TO USE]: Mode 1 ('send'): Send a WhatsApp message or document/image. "
                        "Mode 2 ('fetch'): Read and retrieve past WhatsApp chat history with a contact.\n"
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
                                description="MANDATORY. Contact name OR full phone number with country code."
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
                    name="image_command",
                    description=(
                        "[WHEN TO USE]: Use to generate a new AI image from a text prompt ('generate') "
                        "or edit an existing local image file ('edit')."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be exactly 'generate' or 'edit'."),
                            "prompt": types.Schema(type=types.Type.STRING, description="Detailed visual description of the image to generate/edit."),
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
                        "change volume/brightness, lock/sleep computer, OR take a screen screenshot.\n"
                        "[CRITICAL SCREENSHOT RULE]: If you need to SEE or inspect the user's screen, trigger this tool FIRST "
                        "with system_action='screenshot' and provide a 'screenshot_filename', then inspect it in the next step."
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
                            "system_action": types.Schema(type=types.Type.STRING, description="Must be exactly 'lock', 'sleep', or 'screenshot'."),
                            "screenshot_filename": types.Schema(type=types.Type.STRING, description="Optional: Absolute file path to save screenshot.")
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