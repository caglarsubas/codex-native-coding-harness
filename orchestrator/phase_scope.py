"""Conservative lexical phase scope. Not filesystem or execution authority."""
import fnmatch

from .core import safe_relative


def contained_path(candidate, scopes):
    def valid(path):
        try:
            safe_relative(path)
            return len(path) <= 1000 and not any(ord(c) < 32 or ord(c) == 127 for c in path) and not any(p in ("", ".", "..") for p in path.split("/"))
        except ValueError:
            return False
    if not valid(candidate): return False
    literal = not any(c in candidate for c in "*?[")
    for scope in scopes:
        if not valid(scope): continue
        if candidate == scope or (literal and fnmatch.fnmatchcase(candidate, scope)): return True
        if scope.endswith("/**") and not any(c in scope[:-3] for c in "*?[") and candidate.startswith(scope[:-2]):
            return True
    return False
