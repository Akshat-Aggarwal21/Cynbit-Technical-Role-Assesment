"""Normalization service for standardizing maintenance incident text and attributes."""
import re
from typing import List, Tuple
import datetime

def utc_now() -> datetime.datetime:
    """Return timezone-naive UTC timestamp for standard DB storage without deprecation."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

# Canonical category mapping keywords
CATEGORY_KEYWORDS = {
    "water_intrusion": ["water", "leak", "damp", "dripping", "seepage", "moisture", "ceiling damp", "watermark", "stain"],
    "plumbing": ["pipe", "drain", "toilet", "faucet", "sink", "sewer", "clog", "riser", "burst pipe", "plumbing", "overflow"],
    "hvac": ["ac", "air condition", "heating", "cooling", "thermostat", "chiller", "ventilation", "airflow", "blower"],
    "electrical": ["electric", "power", "breaker", "fuse", "spark", "flicker", "outlet", "wiring", "short circuit"],
    "structural": ["crack", "foundation", "wall crack", "ceiling sag", "beam", "drywall", "balcony"],
    "appliance": ["refrigerator", "fridge", "stove", "oven", "dishwasher", "microwave", "washing machine", "dryer"],
    "security": ["lock", "door handle", "intercom", "keycard", "gate", "window latch"],
}

# Symptom vocabulary mapping
SYMPTOM_PATTERNS = [
    ("water_dripping", [r"drip", r"dripping"]),
    ("water_leakage", [r"leak", r"leaking", r"leakage"]),
    ("ceiling_moisture", [r"ceiling.*damp", r"damp.*ceiling", r"ceiling.*leak", r"stain.*ceiling", r"water mark.*ceiling"]),
    ("standing_water", [r"standing water", r"pool of water", r"flooding", r"flooded"]),
    ("pipe_leak", [r"pipe.*leak", r"riser.*leak", r"leaking.*pipe", r"joint leak"]),
    ("clogged_drain", [r"clog", r"clogged", r"slow drain", r"backed up", r"backup"]),
    ("dampness_odor", [r"damp", r"musty", r"mold", r"mildew", r"odor"]),
    ("no_cooling", [r"no cool", r"blowing warm", r"ac not cooling", r"ac down"]),
    ("no_heating", [r"no heat", r"freezing", r"heater broken"]),
    ("electrical_trip", [r"trip", r"breaker tripped", r"fuse blown", r"power cut"]),
    ("unusual_noise", [r"rattling", r"hammering", r"loud noise", r"strange noise", r"vibration"]),
]

class NormalizationService:
    """Deterministic normalization for maintenance records."""

    @staticmethod
    def clean_text(text: str) -> str:
        """Safely clean whitespace and normalize characters."""
        if not text:
            return ""
        # Remove control characters but preserve standard punctuation
        cleaned = re.sub(r"[\r\n\t]+", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def normalize_category(raw_category: str, description: str) -> str:
        """Map raw category string or infer from description to canonical taxonomy."""
        combined_text = f"{raw_category} {description}".lower()
        
        # Priority check: plumbing & water intrusion
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in combined_text:
                    # Treat plumbing / water_intrusion coherently
                    if cat in ["water_intrusion", "plumbing"]:
                        return "plumbing"
                    return cat

        clean_raw = raw_category.strip().lower().replace(" ", "_")
        return clean_raw if clean_raw else "general_maintenance"

    @staticmethod
    def extract_symptoms(description: str) -> List[str]:
        """Extract standardized symptom tags using deterministic regex patterns."""
        text_lower = description.lower()
        extracted = set()

        for symptom_name, patterns in SYMPTOM_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    extracted.add(symptom_name)
                    break

        # Fallback if no specific symptom regex matched
        if not extracted:
            if "water" in text_lower:
                extracted.add("water_issue")
            elif "noise" in text_lower or "sound" in text_lower:
                extracted.add("unusual_noise")
            else:
                extracted.add("unspecified_symptom")

        return sorted(list(extracted))

    @staticmethod
    def normalize_timestamp(ts: any) -> datetime.datetime:
        """Ensure timestamp is a UTC datetime object."""
        if isinstance(ts, datetime.datetime):
            if ts.tzinfo is not None:
                return ts.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            return ts
        if isinstance(ts, str):
            # Parse ISO or standard formats
            ts_clean = ts.replace("Z", "+00:00")
            try:
                dt = datetime.datetime.fromisoformat(ts_clean)
                if dt.tzinfo is not None:
                    return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                return dt
            except ValueError:
                # Common fallback format: YYYY-MM-DD HH:MM:SS
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
                    try:
                        return datetime.datetime.strptime(ts, fmt)
                    except ValueError:
                        pass
        raise ValueError(f"Unable to parse timestamp: {ts}")
