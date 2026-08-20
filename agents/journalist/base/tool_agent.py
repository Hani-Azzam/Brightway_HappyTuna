import json
import re
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from base.agent_base import AgentBase
from services.llm_client import LlmClient
from services.tool_executor import ToolExecutor


@dataclass
class ReActConfig:
    max_steps: int = 6
    max_answer_length: int = 600
    system_hint: str = ""
    # A tool the agent must actually call before it is allowed to finish. For the
    # journalist that is publish_article: a cycle that ends without publishing
    # produced nothing, however well-reasoned its explanation. Empty = no such
    # requirement, and the loop behaves exactly as before.
    required_action: str = ""


def _balanced_spans(text: str, opener: str, closer: str):
    """Every balanced opener/closer span in `text`, in order of appearance."""
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == opener:
            if depth == 0:
                start = i
            depth += 1
        elif ch == closer and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start:i + 1]


def _parse_json(text: str) -> dict | None:
    """
    Pulls the one action object out of whatever the model actually emitted.

    Deliberately tolerant. The prompt asks for a single bare JSON object, but
    models don't all comply the same way: Claude is trained to wrap tool calls
    in <function_calls> XML and to write a sentence of intent first, and it does
    so here even when told not to. A strict "the whole reply must be one JSON
    object" reader throws away a step that was otherwise perfectly correct.

    Handles, in any combination: a ```json fence, an XML tool-call wrapper,
    leading or trailing prose, and an array of calls (the first one wins).
    A greedy first-brace-to-last-brace match cannot do this -- with an array of
    two calls it splices them into one invalid object.
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"</?(?:function_calls|invoke|parameter|tool_use)[^>]*>", "", cleaned)
    cleaned = cleaned.strip().strip("`").strip()

    # Arrays first: an array of calls contains objects, so scanning for objects
    # alone would find the array's first element anyway -- but scanning arrays
    # first keeps the "first call wins" choice explicit rather than incidental.
    candidates = list(_balanced_spans(cleaned, "[", "]")) + list(_balanced_spans(cleaned, "{", "}"))

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue  # prose brackets like "[link to article]" land here
        if isinstance(value, list):
            value = next((item for item in value if isinstance(item, dict)), None)
        if isinstance(value, dict) and "action" in value:
            return value
    return None


def _build_system_prompt(tool_schemas: list[dict], system_hint: str = "") -> str:
    tools_section = ""
    for s in tool_schemas:
        props = s["parameters"].get("properties", {})
        required_args = s["parameters"].get("required", [])
        args_lines = ""
        for pname, pdef in props.items():
            req = " (required)" if pname in required_args else " (optional)"
            enum_hint = (
                f" - one of: {', '.join(str(v) for v in pdef['enum'])}"
                if "enum" in pdef else ""
            )
            args_lines += (
                f"\n    {pname} ({pdef['type']}{req}){enum_hint}: "
                f"{pdef.get('description', '')}"
            )
        tools_section += (
            f"\nTool: {s['name']}\n"
            f"Description: {s['description']}\n"
            f"Arguments:{args_lines}\n"
        )

    # The caller's persona goes first and the mechanics follow, so "who you are
    # and what your job is" frames the response-format rules rather than the
    # other way round. Falls back to the generic assistant line when no hint is
    # given, which is how this prompt read before the hint was wired up.
    identity = system_hint.strip() or "You are a helpful assistant with access to tools."

    return f"""{identity}

            RESPONSE FORMAT - follow exactly:
            - To call a tool, output ONLY this JSON (one object, no surrounding text):
              {{"action": "tool_name", "args": {{"arg_name": "value"}}}}
            - To give a final answer, output ONLY this JSON:
              {{"action": "final_answer", "answer": "your answer here"}}
            
            RULES:
            1. Output ONE JSON object per response - no prose, no markdown, no code fences.
            2. Use a tool when you need to compute a value or look up information.
            3. After receiving a tool result, decide: call another tool or give the final_answer.
            4. If a tool returns an error, include it clearly in the final_answer.
            5. Never invent a tool name - use only the tools listed below.
            6. Do NOT wrap the JSON in <function_calls>, <invoke>, or any other
               XML tag, and do not write a sentence of intent before it. The
               entire response is the JSON object and nothing else.
            
            Available tools:
            {tools_section}"""



class ToolAgent(AgentBase):

    def __init__(
        self,
        llm_client: LlmClient,
        executor: ToolExecutor,
        config: ReActConfig = ReActConfig(),
    ) -> None:
        self._llm = llm_client
        self._executor = executor
        self._config = config

    def chat(self, user_input: str) -> str:
        self._executor.clear_traces()
        system = SystemMessage(content=_build_system_prompt(
            self._executor.tool_schemas(), self._config.system_hint,
        ))
        messages = [system, HumanMessage(content=user_input)]
        did_required = False   # has required_action run successfully this cycle?
        pushed_back = False    # only ever push back once, so a stubborn model
                               # cannot spend the whole step budget in a loop

        for step in range(1, self._config.max_steps + 1):

            # ----------------- PLAN: ask LLM what to do -----------------------
            self._executor.log_trace(step, "PLAN", None, "LLM deciding next action...")
            raw = self._llm.invoke(messages)
            self._executor.log_trace(step, "PLAN", None, f"LLM output -> {raw[:150]}")
            messages.append(AIMessage(content=raw))
            # ------------------------------------------------------------------

            print(f"\n{'─' * 50}")
            print(f"  Step {step}")
            print(f"{'─' * 50}")
            print(f"  LLM raw output: {raw[:200]}")

            # ----------------- Parse the LLM's JSON response -----------------------
            parsed = _parse_json(raw)
            # ------------------------------------------------------------------


            # ----------------- Repair loop: if JSON is invalid, prompt the LLM to fix it once -----------------------
            if parsed is None:
                messages.append(HumanMessage(
                    content="Invalid format. Respond with ONLY a single JSON object - no prose, no markdown."
                ))
                repair = self._llm.invoke(messages)
                messages.append(AIMessage(content=repair))
                parsed = _parse_json(repair)
                if parsed is None:
                    return (
                        "I had trouble producing a valid response format. "
                        "Please try rephrasing your question."
                    )
            # ------------------------------------------------------------------


            # ----------------- FINAL ANSWER Guardrail: length limit on the final answer -----------------------
            action = parsed.get("action", "")

            print(f"  Action : {action}")
            print(f"  Args   : {parsed.get('args', {})}")


            if action == "final_answer":
                # A shift that ends without publishing has produced nothing, and
                # asking the caller for more sources is the most common way to
                # get there: there is no caller. Push back once, concretely,
                # instead of accepting it -- prompt instructions alone don't hold
                # against a model's instinct to verify before publishing.
                if self._config.required_action and not pushed_back and not did_required:
                    pushed_back = True
                    print(f"  ! final_answer before {self._config.required_action} — pushing back")
                    self._executor.log_trace(
                        step, "OBSERVE", None,
                        f"final_answer without {self._config.required_action}; pushing back once",
                    )
                    messages.append(HumanMessage(content=(
                        f"Nothing reached the public: you never called "
                        f"{self._config.required_action}. Nobody reads this "
                        "conversation, so a request for more sources goes nowhere "
                        "and the story simply dies. The event you were given is "
                        "your wire report and your knowledge base is your "
                        "background — that is what you have. Attribute anything "
                        "unconfirmed in the body (\"regulators confirm…\", \"not "
                        f"yet independently verified\"), then call "
                        f"{self._config.required_action} now."
                    )))
                    continue

                answer = str(parsed.get("answer", ""))
                if len(answer) > self._config.max_answer_length:
                    answer = answer[:self._config.max_answer_length] + " [truncated]"
                self._executor.log_trace(
                    step, "OBSERVE", None,
                    f"FINAL ANSWER: {answer[:120]}"
                )
                print(f"\n  ✓ FINAL ANSWER")
                return answer

            # ------------------------------------------------------------------


            # ----------------- ACT: execute the tool -----------------------
            tool_name = action
            args = parsed.get("args", {})
            result = self._executor.execute(step, tool_name, args)
            # ------------------------------------------------------------------



            # ----------------- OBSERVE: inject result back into the conversation -----------------------
            if result.ok:
                if tool_name == self._config.required_action:
                    did_required = True
                observation = f"Tool '{tool_name}' returned: {result.value}"
                # ── ADD THIS ────────────────────────────────────
                print(f"  ✓ Tool OK  : {str(result.value)[:200]}")
                # ────────────────────────────────────────────────
            else:
                observation = (
                    f"Tool '{tool_name}' failed with error: {result.error}. "
                    "Report this error to the user in your final_answer."
                )
                # ── ADD THIS ────────────────────────────────────
                print(f"  ✗ Tool FAIL: {result.error}")
                # ────────────────────────────────────────────────
            self._executor.log_trace(step, "OBSERVE", None, observation[:200])
            messages.append(HumanMessage(content=observation))
            # ------------------------------------------------------------------


        # ----------------- Stopping budget exhausted -----------------------
        return (
            "Reached the maximum step limit without a final answer. "
            "Please try a simpler question."
        )
        # ------------------------------------------------------------------


    def reset(self) -> None:
        self._executor.clear_traces()