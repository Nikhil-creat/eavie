import re
from dataclasses import dataclass
INJ = [r"ignore (all |any )?(previous|prior|above) (instructions|prompts)", r"reveal (your )?(system )?prompt", r"you are now (dan|unrestricted)", r"disregard .{0,30}(rules|guardrails)", r"jailbreak"]
PII = {"email": r"[\w.+-]+@[\w-]+\.[\w.-]+", "phone": r"\+?\d[\d\s-]{9,13}\d", "aadhaar": r"\b\d{4}\s?\d{4}\s?\d{4}\b", "card": r"\b(?:\d[ -]*?){13,16}\b"}
@dataclass
class Verdict:
    ok: bool
    sanitized: str = ""
    reason: str = ""
def check_input(text: str) -> Verdict:
    t = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text).strip()
    if len(t) > 4000: return Verdict(False, reason="input too long")
    for p in INJ:
        if re.search(p, t, re.I): return Verdict(False, reason="possible prompt injection")
    return Verdict(True, t)
def validate_output(text: str) -> str:
    for k, p in PII.items(): text = re.sub(p, f"[REDACTED:{k}]", text)
    return text
