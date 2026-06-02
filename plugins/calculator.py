"""Calculator plugin — evaluates math expressions."""
import re, math

NAME        = "calculator"
TRIGGERS    = ["calculate", "how much is", "what does", "equals", "solve", "evaluate",
               "square root", "sqrt", "times", "divided by", "plus", "minus"]
# Note: bare operators like " + " are matched in run() via regex, not as triggers
# "what is" removed — too broad, fires on non-math questions
DESCRIPTION = "Evaluates math expressions and calculations"
MANUAL_ONLY = False

def run(query: str, context: dict) -> str:
    text = context["user_input"]
    # Extract expression — look for math-like content
    expr = re.sub(r'[^0-9+\-*/().,\s%^sqrt]', '', text).strip()
    expr = expr.replace("^", "**").replace("sqrt", "math.sqrt")
    expr = re.sub(r'\s+', ' ', expr).strip()
    if not expr or len(expr) < 2:
        return ""
    try:
        # Safe eval with math functions only
        allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
        allowed["abs"] = abs; allowed["round"] = round
        result = eval(expr, {"__builtins__": {}}, allowed)
        return f"{expr} = {result}"
    except Exception:
        return ""
