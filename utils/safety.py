BLOCKED_TERMS = {'suicide','bomb','explode','terror','kill','illegal'}
def contains_blocked(text: str) -> bool:
    if not text: return False
    t = text.lower()
    return any(term in t for term in BLOCKED_TERMS)
def sanitize_output(text: str) -> str:
    if not text: return text
    out = text
    for term in BLOCKED_TERMS:
        out = out.replace(term, '[redacted]')
    return out
