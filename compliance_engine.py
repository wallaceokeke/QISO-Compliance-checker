import pdfplumber
import pytesseract
import json
import os
from PIL import Image
import xml.etree.ElementTree as ET
from fuzzywuzzy import fuzz

ANNEX_PATH = 'data/annex_a_controls.json'
LEARNING_PATH = 'data/learned_responses.json'

# Load Annex A controls
with open(ANNEX_PATH) as f:
    ANNEX_CONTROLS = json.load(f)

# Load learned mappings (Q-table like)
if os.path.exists(LEARNING_PATH):
    with open(LEARNING_PATH) as f:
        LEARNED_RESPONSES = json.load(f)
else:
    LEARNED_RESPONSES = {}

def extract_text(path):
    ext = path.split('.')[-1].lower()
    try:
        if ext == 'pdf':
            with pdfplumber.open(path) as pdf:
                return "\n".join([p.extract_text() or "" for p in pdf.pages])
        elif ext == 'txt':
            return open(path, 'r', encoding='utf-8').read()
        elif ext == 'xml':
            return ET.tostring(ET.parse(path).getroot(), encoding='unicode')
        elif ext == 'png':
            return pytesseract.image_to_string(Image.open(path))
        else:
            return ""
    except Exception as e:
        return f"Error extracting text: {e}"

def match_to_controls(text):
    text = text.lower()
    results = {}
    for control in ANNEX_CONTROLS:
        cid = control['id']
        desc = control['description']
        memory_boost = LEARNED_RESPONSES.get(cid, {}).get(desc, 0)

        # Calculate match score
        score = fuzz.partial_ratio(text, desc.lower()) + memory_boost
        results[cid] = min(score, 100)  # Cap score at 100
    return results

def evaluate_compliance(results, raw_text):
    passed = [cid for cid, score in results.items() if score >= 75]
    failed = [cid for cid in results if cid not in passed]

    # Strict: if any control is missing, it's failed
    is_compliant = len(failed) == 0

    # Score = proportion of matched controls (consistently calculated)
    percent_score = round(len(passed) / len(ANNEX_CONTROLS), 2)

    # Learn from this document (reward the matches)
    for cid in passed:
        desc = next(c['description'] for c in ANNEX_CONTROLS if c['id'] == cid)
        if cid not in LEARNED_RESPONSES:
            LEARNED_RESPONSES[cid] = {}
        LEARNED_RESPONSES[cid][desc] = LEARNED_RESPONSES[cid].get(desc, 0) + 5  # reward by +5

    # Save learned memory
    with open(LEARNING_PATH, 'w') as f:
        json.dump(LEARNED_RESPONSES, f, indent=2)

    return passed, failed, percent_score, is_compliant
