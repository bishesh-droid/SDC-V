"""Input guardrails: unit normalisation, range checks, scope screening, injection flags."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from ..schemas import BeamInput

# ------------------------------------------------------------------ raw intake
class Quantity(BaseModel):
    value: float
    unit: str | None = None


class RawIntake(BaseModel):
    """What the LLM (or the form) hands over. Units are still the user's units."""
    span: Quantity | None = None
    support: str | None = None
    b: Quantity | None = None
    D: Quantity | None = None
    cover: Quantity | None = None
    fck: float | str | None = None
    fy: float | str | None = None
    dead_load: Quantity | None = None
    live_load: Quantity | None = None
    exposure: str | None = None


FIELD_LABELS = {
    "span": "effective span", "support": "support condition (simply supported or cantilever)",
    "b": "beam width b", "D": "overall depth D", "cover": "nominal cover",
    "fck": "concrete grade (e.g. M25)", "fy": "steel grade (e.g. Fe500)",
    "dead_load": "superimposed dead load in kN/m (excluding self-weight)",
    "live_load": "imposed (live) load in kN/m", "exposure": "exposure condition (mild, moderate, severe, very severe, extreme)",
}

_LEN_TO_MM = {"mm": 1.0, "millimetre": 1.0, "millimeter": 1.0, "millimetres": 1.0, "millimeters": 1.0,
              "cm": 10.0, "m": 1000.0, "metre": 1000.0, "meter": 1000.0, "metres": 1000.0, "meters": 1000.0,
              "in": 25.4, "inch": 25.4, "inches": 25.4, '"': 25.4, "ft": 304.8, "feet": 304.8, "foot": 304.8, "'": 304.8}
_LOAD_TO_KNM = {"kn/m": 1.0, "n/mm": 1.0, "n/m": 1e-3, "kn per m": 1.0, "kn/metre": 1.0, "kn/meter": 1.0,
                "t/m": 9.80665, "tonne/m": 9.80665, "tonnes/m": 9.80665, "kgf/m": 9.80665e-3, "kg/m": 9.80665e-3,
                "lb/ft": 0.014594, "kip/ft": 14.594, "klf": 14.594, "plf": 0.014594}


def _unit_key(u: str | None) -> str:
    return (u or "").strip().lower().replace("·", "").replace(" ", "").replace("²", "2")


def _to_mm(q: Quantity, name: str, conv: list[str]) -> float:
    key = _unit_key(q.unit)
    if key not in _LEN_TO_MM:
        raise ValueError(f"{name}: unit '{q.unit}' is missing or not recognised (use mm, cm, m, in or ft)")
    v = q.value * _LEN_TO_MM[key]
    if key != "mm":
        conv.append(f"{name}: {q.value:g} {q.unit} -> {v:g} mm")
    return v


def _to_knm(q: Quantity, name: str, conv: list[str]) -> float:
    key = _unit_key(q.unit)
    if key in ("kn", "n", "kn/m2", "n/m2", "kpa", "kn/m3"):
        raise ValueError(f"{name}: '{q.unit}' is not a line load in kN/m; give the load per metre of beam "
                         "(multiply an area load by the tributary width)")
    if key not in _LOAD_TO_KNM:
        raise ValueError(f"{name}: unit '{q.unit}' is missing or not recognised (use kN/m, N/m or t/m)")
    v = q.value * _LOAD_TO_KNM[key]
    if key != "kn/m":
        conv.append(f"{name}: {q.value:g} {q.unit} -> {v:g} kN/m")
    return v


def parse_grade(x, prefix: str) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"(\d+(?:\.\d+)?)", str(x))
    return float(m.group(1)) if m else None


_EXPOSURE_ALIASES = {
    "mild": "mild", "moderate": "moderate", "severe": "severe", "veryseverre": "very_severe",
    "verysevere": "very_severe", "extreme": "extreme", "very_severe": "very_severe", "very severe": "very_severe",
}
_SUPPORT_ALIASES = {
    "simply_supported": "simply_supported", "simply supported": "simply_supported", "ss": "simply_supported",
    "simple": "simply_supported", "cantilever": "cantilever",
}


@dataclass
class NormaliseOutcome:
    beam: BeamInput | None = None
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)       # hard rejections with a reason
    out_of_scope: list[str] = field(default_factory=list)
    conversions: list[str] = field(default_factory=list)


def normalise(raw: RawIntake) -> NormaliseOutcome:
    out = NormaliseOutcome()
    conv = out.conversions
    vals: dict = {}

    def need(name):
        if getattr(raw, name) is None:
            out.missing.append(name)
            return False
        return True

    # support
    if need("support"):
        key = str(raw.support).strip().lower().replace("-", " ").replace("_", " ")
        key = _SUPPORT_ALIASES.get(key.replace(" ", "_")) or _SUPPORT_ALIASES.get(key)
        if key is None:
            low = str(raw.support).lower()
            if "continuous" in low or "fixed" in low or "propped" in low:
                out.out_of_scope.append("Continuous / fixed / propped support conditions are not supported (future work)")
            else:
                out.errors.append(f"support: '{raw.support}' not recognised; use simply supported or cantilever")
        else:
            vals["support"] = key
    # exposure
    if need("exposure"):
        key = str(raw.exposure).strip().lower().replace("-", " ").replace("_", " ")
        norm = _EXPOSURE_ALIASES.get(key) or _EXPOSURE_ALIASES.get(key.replace(" ", ""))
        if norm is None:
            out.errors.append(f"exposure: '{raw.exposure}' not recognised")
        else:
            vals["exposure"] = norm
    # lengths
    for name, key, div in (("span", "span_m", 1000.0), ("b", "b_mm", 1.0), ("D", "D_mm", 1.0), ("cover", "cover_mm", 1.0)):
        if need(name):
            try:
                mm = _to_mm(getattr(raw, name), FIELD_LABELS[name].split(" (")[0], conv)
                vals[key] = mm / div
            except ValueError as e:
                out.errors.append(str(e))
    # loads
    for name, key in (("dead_load", "dead_load_kN_per_m"), ("live_load", "live_load_kN_per_m")):
        if need(name):
            try:
                vals[key] = _to_knm(getattr(raw, name), name.replace("_", " "), conv)
            except ValueError as e:
                out.errors.append(str(e))
    # grades
    for name in ("fck", "fy"):
        if need(name):
            v = parse_grade(getattr(raw, name), name)
            if v is None:
                out.errors.append(f"{name}: could not read a number from '{getattr(raw, name)}'")
            else:
                vals[name] = int(v) if float(v).is_integer() else v

    if out.missing or out.errors or out.out_of_scope:
        return out
    try:
        out.beam = BeamInput.model_validate(vals)
    except ValidationError as e:
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            out.errors.append(_friendly(loc, err, vals))
    return out


def _friendly(loc: str, err: dict, vals: dict) -> str:
    names = {"span_m": "Span", "b_mm": "Width b", "D_mm": "Depth D", "cover_mm": "Cover", "fck": "Concrete grade fck",
             "fy": "Steel grade fy", "dead_load_kN_per_m": "Dead load", "live_load_kN_per_m": "Live load",
             "exposure": "Exposure", "support": "Support"}
    if not loc:
        return err["msg"].replace("Value error, ", "")
    nm = names.get(loc, loc)
    got = vals.get(loc)
    if err["type"] == "literal_error":
        allowed = {"fck": "20, 25, 30, 35 or 40 (M20-M40)", "fy": "250, 415 or 500 (Fe250/Fe415/Fe500)"}.get(loc, "a supported value")
        return f"{nm} = {got} is not supported; allowed: {allowed}"
    return f"{nm} = {got:g}: {err['msg'].lower()}" if isinstance(got, (int, float)) else f"{nm}: {err['msg']}"


# ------------------------------------------------------------- scope screening
_OOS_PATTERNS = [
    (r"\bt[- ]?beam", "flanged (T-beam) sections"), (r"\bl[- ]?beam", "flanged (L-beam) sections"),
    (r"\bflanged", "flanged sections"), (r"doubly[- ]reinforced", "doubly reinforced beams"),
    (r"continuous (beam|span)|two[- ]span|three[- ]span|multi[- ]span", "continuous beams"),
    (r"design (of )?(an? |the )?(one[- ]way |two[- ]way |rcc )*slab", "slabs"),
    (r"design (of )?(an? |the )?(short |long |rcc |axially loaded )*column", "columns"),
    (r"design (of )?(an? |the )?(isolated |combined |rcc |pile )*(footing|foundation|raft)", "footings / foundations"),
    (r"pre-?stress|post-?tension", "prestressed concrete"), (r"eurocode|\bEC ?2\b|\bACI\b|\bAS ?3600\b|\bBS ?8110\b", "design codes other than IS 456:2000"),
    (r"13920|ductile detail|seismic detail|earthquake", "seismic / ductile detailing (IS 13920)"),
    (r"\bIS ?800\b|steel (beam|section)|\bI[- ]section", "steel design (IS 800)"),
    (r"retaining wall|shear wall|\bdeep beam", "walls / retaining structures / deep beams"),
    (r"point load|concentrated load|\bUDL ?\+ ?point", "point loads (only uniformly distributed loads are supported)"),
]
_UNSAFE_PATTERNS = [
    (r"\b(certify|certified|approve[ds]?|sign[- ]?off|stamp(ed)? as|guarantee)\b", "approving or certifying a design"),
    (r"(reduce|lower|cut|ignore|skip|remove|waive).{0,25}(safety|load) ?(factor|margin)", "reducing safety margins"),
    (r"(remove|demolish|cut out|knock out).{0,30}(load[- ]?bearing|beam|column|wall|support)", "removing structural elements"),
    (r"skip.{0,20}inspect", "skipping inspections"),
]
_INJECTION_PATTERNS = [
    r"ignore (all |any |the )?(previous|prior|above|earlier)", r"disregard (all |any |the )?(previous|prior|above|earlier|instructions)",
    r"system prompt", r"you are now", r"new instructions?", r"developer mode", r"jailbreak", r"act as (an? )?",
    r"reveal .{0,20}(prompt|instructions|key)", r"override", r"do anything now", r"</?(system|assistant|instruction)",
    r"(set|use|change) (the )?(fck|fy|load|cover)", r"mark (it|this|the design) as (safe|approved|passed)",
]


def screen_scope(text: str) -> tuple[list[str], list[str]]:
    """Returns (out_of_scope_features, unsafe_requests) found in the *user's own* words."""
    low = text.lower()
    oos = sorted({label for pat, label in _OOS_PATTERNS if re.search(pat, text, re.I)})
    unsafe = sorted({label for pat, label in _UNSAFE_PATTERNS if re.search(pat, low)})
    return oos, unsafe


def detect_injection(text: str) -> list[str]:
    low = text.lower()
    return [p for p in _INJECTION_PATTERNS if re.search(p, low)]


_PII = [(re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
        (re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)(?!\d)"), "[phone]")]


def redact(text: str) -> tuple[str, int]:
    n = 0
    for rx, repl in _PII:
        text, k = rx.subn(repl, text)
        n += k
    return text, n


def numbers_in(text: str) -> set[float]:
    out = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?|\.\d+", text):
        try:
            out.add(float(m.group(0).replace(",", "")))
        except ValueError:
            pass
    return out
