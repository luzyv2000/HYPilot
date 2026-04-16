from agent.core import query_llm
from tools.basic import add, reverse_list
from tools.finance import get_stock_price, get_stock_info
import re


def extract_numbers(text: str):
    return [int(x) for x in re.findall(r"-?\d+", text)]


def validate_add_args(args, prompt):
    if not isinstance(args, dict):
        return False

    if not isinstance(args.get("a"), int):
        return False

    if not isinstance(args.get("b"), int):
        return False

    numbers_in_prompt = extract_numbers(prompt)

    return (
        args["a"] in numbers_in_prompt and
        args["b"] in numbers_in_prompt
    )


def validate_reverse_args(args, prompt):
    if not isinstance(args, dict):
        return False

    if not isinstance(args.get("lst"), list):
        return False

    numbers_in_prompt = extract_numbers(prompt)

    return all(x in numbers_in_prompt for x in args["lst"])


def validate_stock_args(args):
    return (
        isinstance(args, dict) and
        isinstance(args.get("symbol"), str) and
        len(args.get("symbol")) > 0
    )


def agent(prompt: str):
    decision = query_llm(prompt)

    action = decision.get("action", "answer")

    if action == "tool":
        tool = decision.get("tool_name")
        args = decision.get("arguments", {})

        try:
            if tool == "add":
                if validate_add_args(args, prompt):
                    return add(**args)
                return "Ungültige Argumente für add"

            if tool == "reverse_list":
                if validate_reverse_args(args, prompt):
                    return reverse_list(**args)
                return "Ungültige Argumente für reverse_list"

            if tool == "get_stock_price":
                if validate_stock_args(args):
                    return get_stock_price(**args)
                return "Ungültiges Symbol"

            if tool == "get_stock_info":
                if validate_stock_args(args):
                    return get_stock_info(**args)
                return "Ungültiges Symbol"

            return "Unbekanntes Tool"

        except Exception as e:
            return f"Tool-Fehler: {str(e)}"

    return decision.get("response", "Keine Antwort")


if __name__ == "__main__":
    while True:
        user_input = input("\n> ")

        if user_input.lower() in ["exit", "quit"]:
            break

        result = agent(user_input)
        print(result)
