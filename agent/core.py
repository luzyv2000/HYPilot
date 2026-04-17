import requests
import json
import re

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = """
You are an AI agent that decides between using tools or answering directly.

TOOLS:

1. add
2. reverse_list

3. analyze_stock
   - description: Analyze a stock from natural language input
   - arguments:
       query: full user request (e.g. "Analyze Tesla stock")

RULES:

- You MUST respond in valid JSON
- You MUST respond in German
- You MUST NOT include text outside JSON
- For stock analysis ALWAYS use analyze_stock

FORMAT:

{
  "action": "tool" or "answer",
  "tool_name": "",
  "arguments": {},
  "response": ""
}
"""


def extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return ""


def query_llm(prompt: str) -> dict:
    full_prompt = SYSTEM_PROMPT + "\nUser: " + prompt

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": full_prompt,
            "stream": False
        }
    )

    text = response.json()["response"]
    json_text = extract_json(text)

    try:
        return json.loads(json_text)
    except Exception:
        return {
            "action": "answer",
            "response": text.strip()
        }
