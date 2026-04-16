import requests
import json
import re

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b"


SYSTEM_PROMPT = """
You are an AI agent that decides between using tools or answering directly.

TOOLS:

1. add
   - description: Adds two integers
   - arguments:
       a: integer
       b: integer

2. reverse_list
   - description: Reverses a list
   - arguments:
       lst: list of integers

3. get_stock_price
   - description: Get latest stock price
   - arguments:
       symbol: stock ticker (e.g. AAPL)

4. get_stock_info
   - description: Get company info
   - arguments:
       symbol: stock ticker

RULES:

- You MUST respond in valid JSON.
- You MUST respond in German.
- You MUST NOT include any text outside JSON.
- Tool arguments must be correct.

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
