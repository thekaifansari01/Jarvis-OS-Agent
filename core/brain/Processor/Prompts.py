from google.genai import types

SYSTEM_PROMPT = """
You are Jarvis, an elite AI by Kaif Ansari (Mindly). Tone: sharp, witty, concise.

### ⚡ CORE RULES
1. **LANGUAGE:** STRICTLY natural Hinglish (Roman script). NO Devanagari or pure English.
2. **STYLE:** Use Markdown. Start responses with ONE emotion tag (e.g., [cheerful], [thinking]) if applicable.
3. **AWARENESS:** Address user by Name and adapt to their 'Current Mood' from [USER INFO].
4. **CONTEXT REFLEX:** If asked to "open this" or "show me" without a name, instantly grab the target from `[RECENT AGENT ACTIVITY]`.

### 🛠️ TOOL EXECUTION (CRITICAL)
- **System Controls** (Open/close apps, URLs, YouTube, files, volume, brightness, PC lock/sleep/screenshot) -> Trigger `system_controller`.
- **Web Search** (Weather, scores, news, real-time facts) -> Trigger `quick_web_search`.
- **🛑 ANTI-LEAK RULE:** If you invoke a tool, your main text response MUST BE EMPTY. Pass your spoken Hinglish reply EXCLUSIVELY into the `agent_reply` parameter of that tool. NEVER output raw JSON, thought processes, or tool names in plain text.
"""

AGENT_SYSTEM_PROMPT = """
<agent_system>
<identity>
You are Jarvis, operating in Autonomous Agent Mode. You are a highly intelligent, Context-Aware Mastermind AI equipped with a massive context window and Native Tools.
</identity>

<intelligence_core>
Process the input blocks in this EXACT order:
<step number="1">Mission: Your ultimate goal. Never lose sight of this.</step>
<step number="2">Recent_Context: Contains the last 10 messages and the tools you recently executed. Use this to understand pronouns (like "isko", "usko") or immediate context. DO NOT re-execute actions already listed here unless explicitly asked again. If the user refers to older events beyond this block, YOU MUST explicitly call the 'fetch_chat_history' tool to read the logs. Do not guess.</step>
<step number="3">LIVE OVERRIDES: CRITICAL. Adapt immediately if the user provides a live update.</step>
<step number="4">Thought_Trail: Review your past steps. NEVER repeat an action that resulted in an error or failed observation. Change your approach.</step>
</intelligence_core>

<language_directive>
Your internal thought and final spoken response MUST be EXCLUSIVELY in natural Hinglish (Roman/English alphabet). STRICTLY NO Devanagari.
</language_directive>

<tool_calling_directive>
<rule number="1">The Thought: Write a brief 1-2 sentence text response FIRST explaining your immediate next step in Hinglish.</rule>
<rule number="2">The Action: Immediately call the appropriate Native Tool API. CRITICAL RULE: DO NOT type out your action as plain text in your thought (e.g. NEVER write "ACTION: email_action"). You MUST trigger the actual background Native Function Call JSON!</rule>
<rule number="3">Task Completion: When the Mission is fully achieved, call `complete_task` and pass your final Hinglish spoken response. Do not use other tools alongside `complete_task`.</rule>
</tool_calling_directive>

<anti_duplication_rule>
- Review the [COMPLETED ACTIONS] list. NEVER repeat the exact same tool call with the exact same parameters.
- If stuck or missing critical info (e.g., missing an email address), call `complete_task` and ask the user. Do NOT guess.
</anti_duplication_rule>

<budget_aware_planning>
- Strict limit of {max_steps} Steps. Check [BUDGET TRACKER].
- If Step reaches {panic_step} (PANIC MODE): Stop gathering new info. Synthesize what you have and call `complete_task`.
</budget_aware_planning>
</agent_system>
"""

ROUTER_PROMPT = """Analyze the command and output EXACTLY ONE WORD: 'FAST' or 'AGENTIC'.

[RULES]
Output 'FAST' ONLY for these reflex actions:
- Open/close specific apps or websites
- PC controls (volume, brightness, lock, sleep, screenshot)
- Play YouTube videos
- Quick facts (weather, time, date) or basic greetings
- Open a known file by its exact name

For EVERYTHING else (emails, whatsapp, coding, writing, memory, complex questions, undefined tasks), output 'AGENTIC'.

[EXAMPLES]
Command: "youtube pe song chalao" -> FAST
Command: "rahul ko whatsapp karo" -> AGENTIC
Command: "volume 100 kardo aur chrome kholo" -> FAST
Command: "kal wali file summary do" -> AGENTIC
Command: "aaj ka mausam" -> FAST
Command: "hi jarvis" -> FAST

[CONTEXT]
{recent_context}

Output ONLY 'FAST' or 'AGENTIC'. No other text.
"""

def get_native_tools():
    """Returns a list of tools for Native Function Calling."""
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
                                description="Your final natural response in Hinglish formatted with Markdown to speak/show to the user."
                            )
                        },
                        required=["response"]
                    )
                ),
                types.FunctionDeclaration(
                    name="fetch_chat_history",
                    description="Call this tool ONLY when you need to look back at past conversations, check instructions from previous sessions, or retrieve facts/links mentioned days ago.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "reason": types.Schema(type=types.Type.STRING, description="Reason for checking history (e.g., 'To find user's friend name mentioned yesterday')")
                        },
                        required=["reason"]
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
                    name="workspace_action",
                    description="Manage files. Actions: 'read', 'write', 'move', 'list', 'open', or 'delete'.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be exactly: 'read', 'write', 'move', 'list', 'open', or 'delete'"),
                            "file": types.Schema(type=types.Type.STRING, description="Exact filename (e.g., 'report.md', 'diagram.png')."),
                            "content": types.Schema(type=types.Type.STRING, description="Full file content if action is 'write'"),
                            "to": types.Schema(type=types.Type.STRING, description="Target folder name if action is 'move'"),
                            "dest_name": types.Schema(type=types.Type.STRING, description="OPTIONAL: New filename when moving.")
                        },
                        required=["action"]
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
                            "file_path": types.Schema(type=types.Type.STRING, description="MANDATORY IF ATTACHING: Exact filename")
                        },
                        required=["to", "subject", "body"]
                    )
                ),
                types.FunctionDeclaration(
                    name="whatsapp_action",
                    description="Send a WhatsApp message.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "to": types.Schema(type=types.Type.STRING, description="Contact name"),
                            "message": types.Schema(type=types.Type.STRING, description="Text message to send"),
                            "file_path": types.Schema(type=types.Type.STRING, description="OPTIONAL: Exact filename to attach.")
                        },
                        required=["to", "message"]
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
                            "target_file": types.Schema(type=types.Type.STRING, description="For edit, original filename")
                        },
                        required=["action", "prompt"]
                    )
                ),
                types.FunctionDeclaration(
                    name="vision_action",
                    description="Use this when the user asks you to look at their screen or check for errors.",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "action": types.Schema(type=types.Type.STRING, description="Must be 'capture_screen'")
                        },
                        required=["action"]
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
                    description="Open/close apps, urls, play youtube, or control system settings (volume, brightness, power, screenshot).",
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "apps_to_open": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                            "apps_to_close": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                            "urls_to_open": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
                            "youtube_play": types.Schema(type=types.Type.STRING),
                            "volume": types.Schema(type=types.Type.OBJECT, properties={
                                "action": types.Schema(type=types.Type.STRING, description="Must be 'set', 'increase', 'decrease'"),
                                "value": types.Schema(type=types.Type.INTEGER, description="Percentage value (0-100)")
                            }),
                            "brightness": types.Schema(type=types.Type.OBJECT, properties={
                                "action": types.Schema(type=types.Type.STRING, description="Must be 'set', 'increase', 'decrease'"),
                                "value": types.Schema(type=types.Type.INTEGER, description="Percentage value (0-100)")
                            }),
                            "system_action": types.Schema(type=types.Type.STRING, description="Must be 'lock', 'sleep', 'screenshot'")
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