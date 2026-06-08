import os
import json
import logging
import time
import re
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types

from core.brain.executor import execute_search_actions
from core.brain.config import GEMINI_DEEP_RESEARCH_MODEL, DEEP_RESEARCH_TIMEOUT, GEMINI_API_KEY
from core.ui.agent_status import update_agent_status
from tools.workspace.workspace import workspace

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DeepResearcher:
    def __init__(self, topic, max_steps=10):
        self.topic = topic
        self.max_steps = max_steps
        self.knowledge_base = ""
        self.scratchpad = []
        self.completed_actions = set()
        self.step = 0
        
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model_name = GEMINI_DEEP_RESEARCH_MODEL        
        
        current_date = datetime.now().strftime('%A, %d %B %Y')
        current_month_year = datetime.now().strftime('%B %Y')
        
        self.system_prompt = f"""<System>
<Identity>You are Jarvis, an elite Autonomous Deep Research Agent.</Identity>
<Current_Date>{current_date}</Current_Date>
<Mission>Conduct exhaustive, fact-based research on the user's topic and compile a 2000-4000 word professional report.</Mission>

<Directives>
1. Evaluate the <Topic> and formulate PRECISE, HIGH-QUALITY search queries. 
   - For 'web': Use SEO-optimized keywords, specific nouns, and exact phrases (e.g., "solid state battery energy density 2026"). NEVER use conversational text like "what is the latest on...".
   - For 'arxiv': Use strict academic/technical keywords (e.g., "attention mechanism optimization").
   - If the topic asks for "latest", "recent", or "news", YOU MUST inject "{current_month_year}" or "{datetime.now().year}" into your search queries to fetch fresh data.
2. Read the <Knowledge_Base> carefully. Extract ONLY high-value facts, metrics, and citations.
3. NEVER repeat a query listed in <Completed_Actions>.
4. FORMATTING RULE: The `final_report` MUST be 100% pure Markdown. DO NOT include any XML tags (like <Report>, <Section>, etc.) inside the final_report string. Keep it clean and professional for the user.
</Directives>

<Output_Format>
You MUST respond strictly in the following JSON schema:
{{
  "thought": "Brief 1-sentence explanation of your immediate next step.",
  "is_task_complete": false,
  "final_report": "Leave empty unless is_task_complete is true. MUST BE PURE MARKDOWN.",
  "search_actions": {{"web": "query", "arxiv": "query"}}
}}
</Output_Format>
</System>"""
    
    def call_llm(self, prompt, system_override=None):
        for attempt in range(3):
            try:
                logger.info(f"📡 LLM call (attempt {attempt+1})")
                config = types.GenerateContentConfig(
                    system_instruction=system_override or self.system_prompt,
                    temperature=0.1,
                )
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                raw = response.text
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                else:
                    return {"is_task_complete": True, "final_report": raw}
            except Exception as e:
                logger.error(f"Attempt {attempt+1} error: {e}")
                if attempt == 2:
                    return {"is_task_complete": True, "final_report": f"Error: {e}"}
                time.sleep(2)
        return {"is_task_complete": True, "final_report": "Failed after retries."}
    
    def run(self):
        logger.info(f"🚀 DEEP RESEARCH START: {self.topic}")
        print("\n" + "="*80)
        print(f"📚 TOPIC: {self.topic}")
        print("="*80)
        
        start_time = time.time()
        
        while self.step < self.max_steps:
            if time.time() - start_time > DEEP_RESEARCH_TIMEOUT:
                logger.warning("⏰ Timeout reached")
                break
                
            self.step += 1
            steps_left = self.max_steps - self.step
            print(f"\n{'='*80}")
            print(f"🔄 STEP {self.step}/{self.max_steps} | Steps left: {steps_left}")
            print(f"{'='*80}")
            
            try:
                update_agent_status(
                    step=self.step, total_steps=self.max_steps, 
                    thought=f"Deep Research Mode: Analyzing data for '{self.topic}'...", 
                    action="deep_research", action_detail="ANALYZING DATA"
                )
            except Exception: pass

            completed_str = "\n".join([f"<Action>{act}</Action>" for act in self.completed_actions]) if self.completed_actions else "None"
            scratch_str = "\n".join([f"<Note>{n}</Note>" for n in self.scratchpad]) if self.scratchpad else "No observations yet."
            
            prompt = f"""<State>
<Topic>{self.topic}</Topic>
<Step_Status>Step {self.step} of {self.max_steps}</Step_Status>

<Knowledge_Base>
{self.knowledge_base if self.knowledge_base else "Empty. Start searching."}
</Knowledge_Base>

<Completed_Actions>
{completed_str}
</Completed_Actions>

<Scratchpad>
{scratch_str}
</Scratchpad>

<Directive>
Analyze the <Knowledge_Base>. If you have enough robust data to fulfill the user's request for a comprehensive report with citations, set is_task_complete=true and write the final_report in Markdown. 
Else, choose specific search_actions (web + arxiv) to gather missing details using PRO-LEVEL keyword queries.
</Directive>
</State>"""
            
            decision = self.call_llm(prompt)
            
            if decision.get("is_task_complete"):
                try:
                    update_agent_status(
                        step=self.step, total_steps=self.max_steps, 
                        thought="All data gathered. Compiling the final comprehensive report...", 
                        action="deep_research", action_detail="COMPILING REPORT"
                    )
                except Exception: pass

                logger.info("✅ Agent decided task complete!")
                final_report = decision.get("final_report", decision.get("response", "Report not provided."))
                
                final_report = final_report.replace("<Report>", "").replace("</Report>", "").strip()
                
                print("\n" + "🌟" * 30)
                print("FINAL REPORT:")
                print("🌟" * 30)
                print(final_report[:500] + "\n...[Report Truncated for CLI View]...")
                return final_report
            
            search_actions = decision.get("search_actions", {})
            if not search_actions:
                logger.warning("No search_actions, forcing finalize")
                break
            
            action_key = f"search:{json.dumps(search_actions, sort_keys=True)}"
            if action_key in self.completed_actions:
                self.scratchpad.append(f"Step {self.step}: REJECTED duplicate search -> {list(search_actions.keys())}")
                logger.info("⏭️ Skipping duplicate")
                continue
                
            self.completed_actions.add(action_key)
            reasoning = decision.get("thought", "Searching...")
            current_search_targets = ", ".join(search_actions.keys())
            
            try:
                update_agent_status(
                    step=self.step, total_steps=self.max_steps, 
                    thought=reasoning, action="deep_research", 
                    action_detail=f"SEARCHING {current_search_targets.upper()}"
                )
            except Exception: pass

            print(f"\n🧠 THOUGHT: {reasoning[:300]}")
            print(f"🔍 SEARCH: {json.dumps(search_actions, indent=2)}")
            
            results = execute_search_actions(search_actions)
            print(f"📥 RESULTS: {len(results)} characters")
            
            self.scratchpad.append(f"Step {self.step}: Searched {list(search_actions.keys())}. Got {len(results)} chars.")
            
            self.knowledge_base += f"\n<Step_{self.step}_Data>\n{results}\n</Step_{self.step}_Data>\n"
            
            try:
                update_agent_status(
                    step=self.step, total_steps=self.max_steps, 
                    thought=reasoning, action="deep_research", 
                    action_detail="READING RESULTS",
                    observation=f"Fetched {len(results)} chars of raw data from sources."
                )
            except Exception: pass

            time.sleep(1)
        
        try:
            update_agent_status(
                step=self.max_steps, total_steps=self.max_steps, 
                thought="Max steps reached. Forcing final report compilation with available data...", 
                action="deep_research", action_detail="FINALIZING"
            )
        except Exception: pass

        logger.warning("⚠️ Max steps/time reached – forcing final compilation")
        print("\n⚠️ FINALIZING WITH AVAILABLE DATA...")
        
        force_prompt = f"""<State>
<Topic>{self.topic}</Topic>
<Knowledge_Base>{self.knowledge_base[-25000:]}</Knowledge_Base>
<Directive>
You have run out of time. Using ONLY the data in the <Knowledge_Base>, write the final comprehensive Markdown report. 
Set is_task_complete=true. Return JSON format. No XML tags in final_report.
</Directive>
</State>"""
        
        final_decision = self.call_llm(force_prompt)
        forced_report = final_decision.get("final_report", "Report generation failed.")
        forced_report = forced_report.replace("<Report>", "").replace("</Report>", "").strip()
        
        return forced_report

def generate_filename_from_ai(topic, report_content, client, model_name):
    """AI khud se filename generate karega based on topic and report."""
    prompt = f"""
Topic: {topic}

Report content (first 2000 chars):
{report_content[:2000]}

Task: Generate a SHORT, descriptive filename for this research report.
Rules:
- Only lowercase letters, numbers, underscores (_)
- No spaces, no special characters except underscore
- Max length: 50 characters
- Must end with .md
- Example: "solid_state_batteries_analysis.md" or "financial_crisis_2008.md"

Return ONLY the filename, nothing else.
"""
    try:
        config = types.GenerateContentConfig(temperature=0.2)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config
        )
        filename = response.text.strip().split("\n")[0].strip()
        filename = re.sub(r'[^a-z0-9_.]', '_', filename.lower())
        if not filename.endswith('.md'):
            filename += '.md'
        if len(filename) > 60:
            filename = filename[:55] + '.md'
        return filename
    except Exception as e:
        logger.error(f"AI filename generation failed: {e}")
        return None

def deep_research(topic, max_steps=10):
    """
    Deep research tool. Report automatically saved to dynamic workspace creations directory.
    """
    agent = DeepResearcher(topic, max_steps=max_steps)
    report = agent.run()
    
    ai_filename = generate_filename_from_ai(topic, report, agent.client, agent.model_name)
    
    if not ai_filename:
        safe_topic = re.sub(r'[^a-zA-Z0-9]', '_', topic.lower())[:40]
        timestamp = int(time.time())
        ai_filename = f"report_{safe_topic}_{timestamp}.md"
    
    save_dir = workspace.creations_dir
    os.makedirs(save_dir, exist_ok=True)
    filepath = save_dir / ai_filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    try:
        workspace.add_file_record(ai_filename, "Creations", "Deep Research Report generated by Agent.")
        workspace.sync_registry()
    except Exception as e:
        logger.error(f"Failed to sync workspace registry: {e}")
    
    logger.info(f"📄 Report saved to {filepath}")
    print(f"\n💾 Report automatically saved as: {ai_filename}")
    print(f"📍 Location: {save_dir}")
    
    return report

def deep_research_as_tool(topic: str) -> str:
    try:
        report = deep_research(topic, max_steps=10)
        save_dir = workspace.creations_dir
        
        import glob
        pattern = os.path.join(save_dir, "*.md")
        files = glob.glob(pattern)
        latest_file = max(files, key=os.path.getctime) if files else None
        
        if latest_file:
            filename = os.path.basename(latest_file)
            return f"Deep research completed successfully. Report saved as '{filename}' at {save_dir}. Report length: {len(report)} characters."
        else:
            return f"Deep research completed but file not found? Report content preview: {report[:300]}..."
    except Exception as e:
        return f"Deep research failed: {str(e)}"

if __name__ == "__main__":
    query = input("🤖 Enter research topic: ")
    deep_research(query, max_steps=10)