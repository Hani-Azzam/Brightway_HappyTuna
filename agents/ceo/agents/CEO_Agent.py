import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import re

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from base.agent_base import AgentBase
from services.llm_client import LlmClient
from services.memory import ConversationMemory
from services.tool_executor import ToolExecutor


company_information = (
    "This is some information about the company: Product -> Canned Tuna Products, "
    "Employees -> 500, Annual Revenue -> 250M$, Market Position -> Top 3 tuna brand, "
    "Reputation -> high quality and trusted family brand."
    "## The systems that exist in the simulated world (you reach them through your tools):"
    "1. Internal Chat (chat.*): the company-wide messaging platform for discussions, "
    "announcements, crisis coordination, and employee collaboration. Employees are woken "
    "up when you @mention their agent id (e.g. @EMP-QA-17) in a channel they belong to."
    "2. Customer Support (support.*): handles customer inquiries, complaints, refund "
    "requests, and support tickets."
    "3. Social Network 'BrightTweets' (social.*): the public social platform where "
    "customers and influencers share opinions, react to news, and create trends. "
    "Anything you post there is public and irreversible."
    "4. Social Analytics (analytics.*): the research surface over the social network - "
    "opinion index, crisis meter, sentiment timelines, narratives, spike detection."
    "5. News Portal 'The Daily Catch': a journalism site where an independent journalist "
    "publishes articles about the company. You see its impact through the social network "
    "and the press briefings you receive; you cannot publish there."
    "## The agents that act in this world:"
    "1. CEO (you) - the highest authority within the company. Responsible for strategic "
    "decisions, crisis response, stakeholder communication, and organizational survival. "
    "Your levers: read every system, respond to support tickets (patch), speak publicly "
    "(social posts/comments), and coordinate internally (chat messages, channels)."
    "2. Employees - workers with ids like EMP-QA-17 (QA), PROD-WORKER-3 (production), "
    "PLANT-MGR-1 (plant manager), CONCERNED-EMP-1, WHISTLEBLOWER-1. They report issues, "
    "escalate concerns, respond in chat when mentioned, and handle support tickets."
    "3. Customers - consumer personas who buy or stop buying, open support tickets, and "
    "complain or recommend on the social network."
    "4. Journalist - investigates events and publishes articles on The Daily Catch, then "
    "shares headlines on the social network."
    "5. Influencers - independent opinion leaders on the social network who amplify or "
    "criticize what they see."
)



# =====================================================================
# STEP 1: PROMPT GENERATORS (Helper Functions)
# =====================================================================

def _parse_json(text: str) -> dict | None:
    """Extracts and parses JSON from raw LLM text output."""
    cleaned = re.sub(r"'''(?:json)?\s", "", text).strip().strip("'").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.decoder.JSONDecodeError:
        return None

def _build_planner_prompt(
        tool_schemas: List[Dict[str, Any]],
        user_event: str,
        memory_context: str = "",
) -> str:
    """Generates the initial plan for the CEO agent."""
    tools_summary = "\n".join([f"- {s['name']}: {s['description']}" for s in tool_schemas])

    memory_section = ""
    if memory_context:
        memory_section = f"""
WHAT YOU REMEMBER FROM EARLIER (your own past cycles -- do not repeat actions
already taken; follow up on commitments instead):
{memory_context}
"""

    return f"""You are a CEO Agent in Food Manufacturing Company Named **HappyTuna**. managing corporate operations.
This information about the company and its agents and roles: "{company_information}"
{memory_section}
A major event/problem has occurred: "{user_event}"

Available Tools & Sub-Agents:
{tools_summary}

Task: Break down how to resolve this event into a clear, sequential plan of sub-tasks.
Keep the plan concise (maximum 15 steps), and keep it grounded in the tools that
actually exist above.

RESPONSE FORMAT (JSON ONLY):
{{
  "plan": [
    "Step 1 action description (e.g., read the open safety_concern tickets in the support queue)",
    "Step 2 action description",
    "Step 3 action description"
  ]
}}"""


def _schema_type(prop: Dict[str, Any]) -> str:
    """Names a JSON Schema property's type for the prompt.

    Optional parameters carry no top-level "type" -- they're an anyOf over the
    real type and "null" (e.g. support.patch_ticket's `status`), so indexing
    ["type"] raises KeyError on every tool that has one. Read the first
    non-null branch instead.
    """
    if "type" in prop:
        return prop["type"]

    for branch in prop.get("anyOf", []):
        branch_type = branch.get("type")
        if branch_type and branch_type != "null":
            return branch_type

    return "string"


def _schema_description(prop: Dict[str, Any]) -> str:
    """Reads a JSON Schema property's description for the prompt.

    Same shape of problem as _schema_type: on an optional parameter the
    description is often attached to the anyOf branch that carries the real
    type rather than to the property itself, so reading only the top level
    hands the model a parameter with no explanation of what it does.
    """
    description = prop.get("description")
    if description:
        return description

    for branch in prop.get("anyOf", []):
        branch_description = branch.get("description")
        if branch_description and branch.get("type") != "null":
            return branch_description

    return ""


def _require_sendable_messages(messages: List[Any], step_label: str) -> None:
    """Fails loudly before a request that Gemini would reject as empty.

    Gemini requires at least one entry in `contents`, and answers anything
    else with the opaque "ValueError: contents are required" -- no indication
    of which step or which message list was at fault.

    The trap is a lone SystemMessage: langchain-google-genai routes it to the
    request's `system_instruction` field rather than into `contents`, so a
    message list that looks populated still sends zero content parts.
    """
    def is_blank(message: Any) -> bool:
        content = message.content
        return not (content.strip() if isinstance(content, str) else content)

    if not messages:
        raise ValueError(f"{step_label}: no messages to send to the LLM.")

    if all(is_blank(m) for m in messages):
        raise ValueError(f"{step_label}: every message content is blank.")

    if not any(not isinstance(m, SystemMessage) and not is_blank(m) for m in messages):
        raise ValueError(
            f"{step_label}: only SystemMessage content is present. Gemini needs at "
            "least one non-empty user turn or the request's `contents` goes out empty."
        )


MAX_RESULT_CHARS = 1200


def _render_tool_value(value: Any) -> str:
    """Renders a tool's return value for the step outcome and the prompt history.

    The value is what the next step has to work from -- channel ids, ticket ids,
    post ids -- so it travels with the outcome instead of being summarised away.
    Truncated only to keep one large listing from crowding out the prompt.
    """
    try:
        rendered = json.dumps(value, default=str)
    except (TypeError, ValueError):
        rendered = str(value)

    if len(rendered) > MAX_RESULT_CHARS:
        rendered = f"{rendered[:MAX_RESULT_CHARS]}... (truncated)"
    return rendered


def _describe_exhausted_step(
        attempts: int,
        tool_errors: List[str],
        unusable_replies: int,
) -> str:
    """Says why a step ran out of attempts, in terms of what actually happened.

    Reached only when nothing succeeded, so the two causes are named separately:
    tools that were called and failed, and replies that carried no runnable
    action. "Maximum retries exceeded" covered both and described neither.
    """
    reasons: List[str] = []
    if tool_errors:
        reasons.append(
            f"{len(tool_errors)} tool call(s) were attempted and all failed "
            f"({'; '.join(tool_errors)})"
        )
    if unusable_replies:
        reasons.append(
            f"{unusable_replies} model reply/replies contained no usable action"
        )
    if not reasons:
        reasons.append("the model produced neither a tool call nor a step_complete")

    return (
        f"Step did not complete: no tool call succeeded in {attempts} attempt(s) — "
        + "; ".join(reasons)
        + "."
    )


@dataclass
class StepOutcome:
    """What actually happened in a step.

    `completed` is the honest answer to "did this step do its job", kept
    separate from `summary` so the trace, the history handed to later steps,
    and the final report all read from the same fact.
    """
    completed: bool
    summary: str


def _build_executor_prompt(
        tool_schemas: List[Dict[str, Any]],
        overall_event: str,
        plan: List[str],
        current_step_idx: int,
        previous_results: List[Dict[str, Any]]
) -> str:
    """Focuses the LLM purely on executing ONE specific step of the plan."""
    tools_section = ""
    for s in tool_schemas:
        props = s["parameters"].get("properties", {})
        required_args = s["parameters"].get("required", [])
        # Mark required vs optional explicitly: without it a tool like
        # support.patch_ticket (one required id, four optional fields) looks
        # like every argument is discretionary, and an empty patch reads as a
        # valid call.
        args_lines = "".join([
            f"\n   - {k} ({_schema_type(v)}, "
            f"{'required' if k in required_args else 'optional'})"
            f": {_schema_description(v)}"
            for k, v in props.items()
        ])
        tools_section += f"\nTool: {s['name']}\nDescription: {s['description']}\nArgs:{args_lines}\n"

    formatted_history = "\n".join([
        f"- Step {r['step']} [{'completed' if r['completed'] else 'did not complete'}]: "
        f"{r['task']} --> Outcome: {r['result']}"
        for r in previous_results
    ]) if previous_results else "None"

    return f"""You are the CEO Agent executing a plan.

OVERALL EVENT: {overall_event}
CURRENT PLAN: {json.dumps(plan, indent=2)}

PROGRESS SO FAR (the outcomes below include the real data each tool returned):
{formatted_history}

CURRENT TASK TO COMPLETE NOW: Step {current_step_idx + 1}: "{plan[current_step_idx]}"

RESPONSE FORMAT — follow exactly:
- To call a tool/sub-agent for this step, output:
  {{"action": "tool_name", "args": {{"arg_name": "value"}}}}
- If this step needs no tool call, output:
  {{"action": "step_complete", "result": "Summary of step execution outcome"}}

USING IDS AND OTHER VALUES — this is not optional:
- Every id, channel id, ticket id, post id, email address, and username you pass
  as an argument must be copied EXACTLY from a tool result in PROGRESS SO FAR.
- Never invent an identifier and never substitute a human-readable name for one.
  A channel named "General" in the listing is NOT a valid `channel` argument --
  pass the id that the listing returned for it.
- If the id you need does not appear in any previous result, call the tool that
  lists or looks it up first, and use the id it returns.

One successful tool call completes this step; the plan's next step continues the
work, and the result of this call will be available to it.

Available Tools:
{tools_section}"""


# =====================================================================
# STEP 2: CONFIGURATION & CEO AGENT CLASS
# =====================================================================

@dataclass
class CeoConfig:
    max_tool_retries_per_step: int = 6
    max_plan_steps: int = 15


class CeoAgent(AgentBase):
    def __init__(
            self,
            llm_client: LlmClient,
            executor: ToolExecutor,
            config: CeoConfig = CeoConfig(),
            memory: Optional[ConversationMemory] = None,
    ) -> None:
        self._llm = llm_client
        self._executor = executor
        self._config = config
        self._memory = memory

    def chat(self, user_input: str) -> str:
        self._executor.clear_traces()
        tool_schemas = self._executor.tool_schemas()

        # ==========================================
        # PHASE 1: PLANNING
        # ==========================================
        self._executor.log_trace(0, "PLAN", None, "CEO generating initial plan...")

        memory_context = self._memory.render() if self._memory is not None else ""
        planner_prompt = _build_planner_prompt(tool_schemas, user_input, memory_context)
        raw_plan = self._llm.invoke([HumanMessage(content=planner_prompt)])
        parsed_plan = _parse_json(raw_plan)

        if not parsed_plan or "plan" not in parsed_plan:
            return "Failed to generate a valid operational plan for the event."

        plan: List[str] = parsed_plan["plan"][:self._config.max_plan_steps]
        self._executor.log_trace(0, "PLAN", None, f"Generated Plan: {json.dumps(plan)}")

        # ==========================================
        # PHASE 2: EXECUTION LOOP
        # ==========================================
        previous_results: List[Dict[str, Any]] = []

        for step_idx, step_task in enumerate(plan):
            self._executor.log_trace(
                step_idx + 1, "EXECUTE_STEP", None, f"Starting Step {step_idx + 1}: {step_task}"
            )

            # Execute step with retries for tool calls
            step_outcome = self._execute_single_step(
                user_event=user_input,
                plan=plan,
                current_step_idx=step_idx,
                previous_results=previous_results,
                tool_schemas=tool_schemas,
            )

            previous_results.append({
                "step": step_idx + 1,
                "task": step_task,
                "completed": step_outcome.completed,
                "result": step_outcome.summary,
            })

            # The phase reports what happened, so a step that never finished is
            # not logged as STEP_COMPLETE.
            self._executor.log_trace(
                step_idx + 1,
                "STEP_COMPLETE" if step_outcome.completed else "STEP_INCOMPLETE",
                None,
                f"Outcome: {step_outcome.summary}",
            )

        # ==========================================
        # PHASE 3: FINAL CEO DECISION / SUMMARY
        # ==========================================
        completed_count = sum(1 for r in previous_results if r["completed"])

        summary_prompt = f"""You are the CEO. You have worked through the planned actions for the event: "{user_input}".

Execution Summary ({completed_count} of {len(previous_results)} steps completed):
{json.dumps(previous_results, indent=2)}

Base your report only on this record. Each entry carries a "completed" flag and,
where a tool ran, the data it returned. A step marked completed succeeded — do
not describe it, or the information it retrieved, as unavailable. Report a gap
only where a step is marked not completed, and say which step and why.

Provide a concise final decision/summary report for the executive record."""

        final_response = self._llm.invoke([HumanMessage(content=summary_prompt)])

        if self._memory is not None:
            # Record what actually happened, not just what the model says: the
            # successful tool calls are the ground truth of this cycle.
            actions = [
                f"{t.tool_name} (ok)" for t in self._executor.get_traces()
                if t.phase == "ACT" and t.tool_name and t.details.startswith("OK")
            ]
            outcome = final_response
            if actions:
                outcome = f"Tools used: {', '.join(actions)}. Report: {final_response}"
            self._memory.add(situation=user_input, outcome=outcome)

        return final_response

    def _execute_single_step(
            self,
            user_event: str,
            plan: List[str],
            current_step_idx: int,
            previous_results: List[Dict[str, Any]],
            tool_schemas: List[Dict[str, Any]]
    ) -> StepOutcome:
        """Sub-loop to handle tool calls for a single step in the plan.

        Two different things can go wrong here and they are not the same thing:
        the tool call can fail, or the model can fail to end the loop with a
        step_complete action. Only the first is a failed step. A step whose tool
        call came back OK is done -- reporting it as "maximum retries exceeded"
        put a successful call, and the data it returned, into the record as a
        failure. Where the loop really does run out of attempts, the outcome
        names what actually stopped it.
        """

        exec_system_prompt = _build_executor_prompt(
            tool_schemas, user_event, plan, current_step_idx, previous_results
        )
        step_task = plan[current_step_idx]
        step_label = f'Step {current_step_idx + 1} ("{step_task}")'

        # The SystemMessage carries the tools and context, but Gemini puts it in
        # `system_instruction` -- it never lands in `contents`. Without a user
        # turn alongside it the request is empty. See _require_sendable_messages.
        step_messages = [
            SystemMessage(content=exec_system_prompt),
            HumanMessage(
                content=f'Execute step {current_step_idx + 1}: "{step_task}"\n'
                        f"Respond with a single JSON object in the format specified above."
            ),
        ]

        attempts = self._config.max_tool_retries_per_step
        tool_errors: List[str] = []
        unusable_replies = 0

        for _ in range(attempts):
            _require_sendable_messages(step_messages, step_label)
            raw = self._llm.invoke(step_messages)
            step_messages.append(AIMessage(content=raw))

            parsed = _parse_json(raw)
            if not parsed:
                unusable_replies += 1
                step_messages.append(
                    HumanMessage(content="Invalid JSON format. Respond with a valid single JSON object.")
                )
                continue

            action = parsed.get("action", "")

            # If LLM finishes the current step without needing a tool:
            if action == "step_complete":
                summary = str(parsed.get("result", "Step finished."))
                if tool_errors:
                    summary += (
                        f" (No tool call succeeded during this step; "
                        f"{len(tool_errors)} failed: {'; '.join(tool_errors)}.)"
                    )
                return StepOutcome(completed=True, summary=summary)

            if not action:
                unusable_replies += 1
                step_messages.append(HumanMessage(
                    content='The JSON had no "action". Respond with either a tool call '
                            'or {"action": "step_complete", "result": "..."}.'
                ))
                continue

            # Execute tool call for this step
            tool_name = action
            args = parsed.get("args", {})
            result = self._executor.execute(current_step_idx + 1, tool_name, args)

            # A call that came back OK is the step's work, done. Returning here
            # carries the returned data into the record instead of leaving it to
            # a later summary, and stops a side-effecting tool (create_post,
            # send_email) from being called a second time on the next attempt.
            if result.ok:
                return StepOutcome(
                    completed=True,
                    summary=(
                        f"Called {tool_name} with args="
                        f"{json.dumps(args, default=str)}; it succeeded and returned: "
                        f"{_render_tool_value(result.value)}"
                    ),
                )

            tool_errors.append(f"{tool_name}: {result.error}")
            step_messages.append(
                HumanMessage(content=f"Tool '{tool_name}' failed: {result.error}")
            )

        return StepOutcome(
            completed=False,
            summary=_describe_exhausted_step(attempts, tool_errors, unusable_replies),
        )

    def reset(self) -> None:
        self._executor.clear_traces()