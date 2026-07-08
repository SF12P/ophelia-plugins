"""Calculator plugin — evaluates math expressions."""
import re, math

NAME        = "calculator"
TRIGGERS    = ["calculate", "how much is", "what does", "equals", "solve", "evaluate",
               "square root", "sqrt", "times", "divided by", "plus", "minus"]
# Note: bare operators like " + " are matched in run() via regex, not as triggers
# "what is" removed — too broad, fires on non-math questions
DESCRIPTION = "Evaluates math expressions and calculations"
MANUAL_ONLY = False
AUTHOR    = "SF12P"
TAGS      = ['utility', 'math']
REQUIRES  = []


def run(query: str, context: dict) -> str:
    text = context["user_input"]
    # Extract expression — look for math-like content
    expr = re.sub(r'[^0-9+\-*/().,\s%^sqrt]', '', text).strip()
    expr = expr.replace("^", "**").replace("sqrt", "math.sqrt")
    expr = re.sub(r'\s+', ' ', expr).strip()
    if not expr or len(expr) < 2:
        return ""
    # Guard against runaway expressions (e.g. 9**9**9) that can hang
    # or exhaust memory: cap length, allow a single exponentiation,
    # and require its exponent to be a small plain integer.
    if len(expr) > 80:
        return ""
    if "**" in expr:
        if expr.count("**") > 1:
            return ""
        m = re.search(r'\*\*\s*(\d{1,4})(?![\d.(])', expr)
        if not m or int(m.group(1)) > 1000:
            return ""
    try:
        # Safe eval with math functions only
        allowed = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
        allowed["abs"] = abs; allowed["round"] = round
        result = eval(expr, {"__builtins__": {}}, allowed)
        return f"{expr} = {result}"
    except Exception:
        return ""
