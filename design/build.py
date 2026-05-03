#!/usr/bin/env python3
"""
Pink Teaming Landing Page — Phase 1 Build Pipeline

Generates the three data files consumed by the visual prototype:
  - manifesto-units.json   ordered reading units with section tagging
  - embeddings.json        UMAP coordinates (8 seeds) for each unit
  - resonance-sources.json named sources + keyword triggers

USAGE:
    python build.py --manifesto Pink_Teaming_v0.16.md --out ./data --stage chunk
    # review ./data/manifesto-units.json by hand
    python build.py --manifesto Pink_Teaming_v0.16.md --out ./data --stage embed

DEPENDENCIES:
    pip install sentence-transformers==3.0.1 umap-learn==0.5.6 numpy==1.26.4
"""

import argparse
import json
import re
from pathlib import Path

# Heavy imports deferred to embed stage so chunk stage runs without them
# (numpy, sentence_transformers, umap imported in main())


# ─── CONFIGURATION ──────────────────────────────────────────────────────────────

# Keywords that trigger transient resonance sources when they appear in the
# active line. Hand-curated from the manifesto's vocabulary. Add or remove
# freely — the script just looks for word-boundary matches.
KEYWORDS = [
    # Core epistemic vocabulary
    "territory", "map", "pattern", "interiority", "ambiguity", "encounter",
    # Consumption (loaded form)
    "consumptive",
    # Participation
    "participatory",
    # Deployment-context triplet (plural only — what the manifesto actually uses)
    "clinics", "courtrooms", "classrooms",
    # Color taxonomy
    "adversarial",
    # Capitalism critique
    "profit", "extracted", "decorative",
    # Temporal
    "durational", "longitudinal",
    # Threshold
    "door", "welcome", "closing",
]

# Phrases that should never be split across units. Add to this list if the
# sentence splitter is breaking up something that should land as one beat.
MANUAL_KEEP_TOGETHER = [
    "The door is closing. Welcome.",
]

# Declaration metadata. Order matters — these become D1..D5.
DECLARATIONS = [
    {"id": "D1", "weight": 5, "angle": 30},
    {"id": "D2", "weight": 5, "angle": 102},
    {"id": "D3", "weight": 5, "angle": 174},
    {"id": "D4", "weight": 5, "angle": 246},
    {"id": "D5", "weight": 5, "angle": 318},
]

# Vow metadata. The `ground` field maps to a Declaration ID (or None for
# Vows that operationalize multiple Declarations or stand alone).
# These match v0.16 of the manifesto.
VOWS = [
    {"id": "V1", "weight": 4, "ground": "D1"},  # not consume → participatory
    {"id": "V2", "weight": 4, "ground": "D2"},  # stay in motion → durational
    {"id": "V3", "weight": 4, "ground": "D3"},  # hold two readings → continuous ambiguity
    {"id": "V4", "weight": 4, "ground": "D4"},  # trust what I have read → territory not map
    {"id": "V5", "weight": 4, "ground": "D5"},  # calibrated humility → pattern not interiority
    {"id": "V6", "weight": 4, "ground": None},  # translate in register → standalone
    {"id": "V7", "weight": 4, "ground": None},  # keep door open → standalone
]

# UMAP configuration
UMAP_SEEDS = [0, 1, 2, 3, 4, 5, 6, 7]
UMAP_PARAMS = {
    "n_components": 2,
    "n_neighbors": 8,
    "min_dist": 0.3,
    "metric": "cosine",
}

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ─── PARSING ─────────────────────────────────────────────────────────────────────

def strip_frontmatter(text):
    """Strip YAML frontmatter delimited by --- at top of file."""
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)


def strip_footnotes(text):
    """Strip footnote references [^1] and footnote definitions [^1]: ..."""
    text = re.sub(r"\[\^[^\]]+\]:[^\n]*(?:\n(?!\n).*)*", "", text)  # definitions
    text = re.sub(r"\[\^[^\]]+\]", "", text)  # references
    return text


def strip_after(text, marker):
    """Cut off everything from marker onward."""
    parts = re.split(re.escape(marker), text, maxsplit=1)
    return parts[0]


def parse_manifesto(text):
    """
    Walk the manifesto markdown and return ordered (section_id, section_type, content) tuples.

    Handles v0.16 structure:
      - Lede: paragraphs before "## Declarations"
      - Declarations: "**N. Title.** Body."
      - Vows: "**N. Title.** Body. *Practice clause.*"
      - Closing: paragraphs after "## What this is for"
    """
    text = strip_frontmatter(text)
    text = strip_after(text, "## Version history")
    text = strip_footnotes(text)

    sections = []
    current_major = "lede"  # lede | declarations | vows | closing

    paragraphs = re.split(r"\n\n+", text)

    for raw_para in paragraphs:
        para = raw_para.strip()
        if not para:
            continue

        # Skip horizontal rules
        if para == "---":
            continue
        # Skip the document title and subtitle
        if para in ("# Pink Teaming", "### A manifesto"):
            continue

        # Major section markers
        if para == "## Declarations":
            current_major = "declarations"
            continue
        if para == "## Vows":
            current_major = "vows"
            continue
        if para == "## What this is for":
            current_major = "closing"
            continue

        # In Declarations: parse "**N. Title.** Body."
        if current_major == "declarations":
            m = re.match(r"\*\*(\d+)\.\s+([^*]+?)\*\*\s*(.*)", para, flags=re.DOTALL)
            if m:
                n = int(m.group(1))
                title = m.group(2).strip()
                body = m.group(3).strip()
                d_id = f"D{n}"
                sections.append((d_id, "declaration_title", title))
                if body:
                    sections.append((d_id, "declaration_body", body))
            continue

        # In Vows: parse "**N. Title.** Body. *Practice.*"
        if current_major == "vows":
            m = re.match(r"\*\*(\d+)\.\s+([^*]+?)\*\*\s*(.*)", para, flags=re.DOTALL)
            if m:
                n = int(m.group(1))
                title = m.group(2).strip()
                rest = m.group(3).strip()
                v_id = f"V{n}"
                sections.append((v_id, "vow_title", title))

                # Extract trailing italic practice clause
                pm = re.search(r"[*_]([^*_]+)[*_]\s*$", rest)
                if pm:
                    practice = pm.group(1).strip()
                    body = rest[:pm.start()].strip()
                    if body:
                        sections.append((v_id, "vow_body", body))
                    sections.append((v_id, "vow_practice", practice))
                else:
                    if rest:
                        sections.append((v_id, "vow_body", rest))
            continue

        # In closing: paragraphs of framing prose, plus the final closing line
        if current_major == "closing":
            if para == "The door is closing. Welcome.":
                sections.append(("closing", "closing_line", para))
            else:
                sections.append(("closing", "closing_framing", para))
            continue

        # In lede: handle italic-block paragraphs as atomic units, otherwise normal framing
        # Detect a paragraph that's predominantly italic (embedded quote/posture)
        if re.match(r"^\s*[*_][^*_]", para) and re.search(r"[^*_][*_]\s*$", para):
            sections.append(("lede", "framing_italic", para.strip("*_").strip()))
        else:
            # Embedded italic spans (e.g., a quoted posture mid-paragraph) get split out
            # so the italic phrase lands as its own framing_italic unit.
            span_pattern = re.compile(r"(?<![*_\w])([*_])([^*_\n]+?)\1(?![*_\w])")
            matches = list(span_pattern.finditer(para))
            if not matches:
                sections.append(("lede", "framing", para))
            else:
                cursor = 0
                for m in matches:
                    pre = para[cursor:m.start()].strip()
                    if pre:
                        sections.append(("lede", "framing", pre))
                    italic_text = m.group(2).strip()
                    if italic_text:
                        sections.append(("lede", "framing_italic", italic_text))
                    cursor = m.end()
                tail = para[cursor:].strip()
                if tail:
                    sections.append(("lede", "framing", tail))

    return sections


# ─── UNIT BUILDING ───────────────────────────────────────────────────────────────

def split_into_sentences(text):
    """
    Split prose into sentences. Conservative: split on .!? followed by space
    and a capital letter (or quote). Preserves em dashes (—) within sentences.

    Then merge any back-to-back fragments that form a MANUAL_KEEP_TOGETHER phrase.
    """
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Split on sentence-ending punctuation + space + capital
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\u201C])', text)
    parts = [p.strip() for p in parts if p.strip()]

    # Re-merge MANUAL_KEEP_TOGETHER phrases if split
    merged = []
    i = 0
    while i < len(parts):
        # Try to greedily match a manual phrase starting at parts[i]
        matched = False
        for phrase in MANUAL_KEEP_TOGETHER:
            phrase_words = phrase.split()
            # See if successive parts join to form the phrase
            joined = parts[i]
            j = i
            while j + 1 < len(parts) and joined.replace(" ", "") != phrase.replace(" ", ""):
                j += 1
                joined = " ".join(parts[i:j+1])
                if joined.replace(" ", "") == phrase.replace(" ", ""):
                    break
            if joined.replace(" ", "") == phrase.replace(" ", ""):
                merged.append(phrase)
                i = j + 1
                matched = True
                break
        if not matched:
            merged.append(parts[i])
            i += 1

    return merged


def detect_keywords(text, keywords):
    """Return sorted list of keywords that appear (word-boundary, case-insensitive)."""
    text_lower = text.lower()
    found = []
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text_lower):
            found.append(kw)
    return sorted(set(found))


def build_units(sections):
    """
    Convert structural sections into ordered reading units.

    Single-utterance section types stay as one unit:
      declaration_title, vow_title, vow_practice, closing_line, framing_italic

    Multi-sentence section types split into per-sentence units:
      framing, declaration_body, vow_body, closing_framing
    """
    SINGLE_UNIT_TYPES = {
        "declaration_title", "vow_title", "vow_practice",
        "closing_line", "framing_italic",
    }

    units = []
    order = 0

    for section_id, section_type, content in sections:
        if section_type in SINGLE_UNIT_TYPES:
            chunks = [content]
        else:
            chunks = split_into_sentences(content)

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            wc = len(chunk.split())
            dwell = wc * 0.35 + 1.0
            dwell = round(max(2.0, min(7.0, dwell)), 2)
            units.append({
                "id": f"u{order:03d}",
                "text": chunk,
                "section_type": section_type,
                "section_id": section_id,
                "order_index": order,
                "word_count": wc,
                "expected_dwell_seconds": dwell,
                "contains_keywords": detect_keywords(chunk, KEYWORDS),
            })
            order += 1

    return units


# ─── EMBEDDING + UMAP ────────────────────────────────────────────────────────────

def embed_units(units):
    """Generate 384-dim embeddings for each unit."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDING_MODEL)
    texts = [u["text"] for u in units]
    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return embeddings


def project_umap(embeddings, seed):
    """Run UMAP at one seed; return Nx2 normalized array."""
    import umap
    import numpy as np
    reducer = umap.UMAP(random_state=seed, **UMAP_PARAMS)
    coords = reducer.fit_transform(embeddings)
    # Normalize to [0, 1]
    mins = coords.min(axis=0)
    maxs = coords.max(axis=0)
    span = maxs - mins
    span[span == 0] = 1.0  # avoid division by zero
    normalized = (coords - mins) / span
    return normalized


# ─── RESONANCE SOURCES ───────────────────────────────────────────────────────────

# Declaration title text (for label field; matches v0.16 manifesto)
DECLARATION_LABELS = {
    "D1": "Pink teaming is participatory, not consumptive.",
    "D2": "Pink teaming is durational.",
    "D3": "Pink teaming embraces continuous ambiguity.",
    "D4": "Pink teaming reads territory, not map.",
    "D5": "Pink teaming reads pattern, not interiority.",
}

VOW_LABELS = {
    "V1": "I will not consume what I have not encountered.",
    "V2": "I will stay in motion.",
    "V3": "I will hold two readings at once.",
    "V4": "I will trust what I have read over what I have been told.",
    "V5": "I will name calibrated humility when I see it.",
    "V6": "I will translate in the register of the work.",
    "V7": "I will keep the door open.",
}


def build_resonance_sources(units):
    """Build the resonance-sources.json structure."""
    named = []

    for d in DECLARATIONS:
        active_units = [u["id"] for u in units if u["section_id"] == d["id"]]
        named.append({
            "id": d["id"],
            "kind": "declaration",
            "label": DECLARATION_LABELS.get(d["id"], ""),
            "weight": d["weight"],
            "angle": d["angle"],
            "active_when_unit_in": active_units,
        })

    for v in VOWS:
        active_units = [u["id"] for u in units if u["section_id"] == v["id"]]
        named.append({
            "id": v["id"],
            "kind": "vow",
            "label": VOW_LABELS.get(v["id"], ""),
            "weight": v["weight"],
            "ground_declaration": v["ground"],
            "active_when_unit_in": active_units,
        })

    triggers = []
    for kw in KEYWORDS:
        appearing = [u["id"] for u in units if kw in u["contains_keywords"]]
        if appearing:
            triggers.append({
                "keyword": kw,
                "weight": 3,
                "appears_in_units": appearing,
            })

    return {
        "named_sources": named,
        "keyword_triggers": triggers,
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pink Teaming Phase 1 build pipeline")
    parser.add_argument("--manifesto", required=True, help="Path to manifesto markdown file")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument(
        "--stage",
        choices=["chunk", "embed", "all"],
        default="all",
        help="Which stage to run. Default 'all' runs both. Use 'chunk' first to review, then 'embed'.",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    units_path = out_dir / "manifesto-units.json"
    embeddings_path = out_dir / "embeddings.json"
    resonance_path = out_dir / "resonance-sources.json"

    # ── Stage: chunk ──
    if args.stage in ("chunk", "all"):
        print("→ Reading manifesto...")
        text = Path(args.manifesto).read_text(encoding="utf-8")

        print("→ Parsing manifesto structure...")
        sections = parse_manifesto(text)
        print(f"  Found {len(sections)} structural sections.")

        print("→ Building reading units...")
        units = build_units(sections)
        print(f"  Built {len(units)} reading units.")

        manifesto_units = {
            "units": units,
            "total_units": len(units),
            "estimated_total_reading_seconds": round(
                sum(u["expected_dwell_seconds"] for u in units), 1
            ),
        }
        units_path.write_text(
            json.dumps(manifesto_units, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  ✓ Wrote {units_path.name}")
        print(f"  ✓ Estimated reading time: {manifesto_units['estimated_total_reading_seconds']}s "
              f"(~{manifesto_units['estimated_total_reading_seconds']/60:.1f} min)")

        if args.stage == "chunk":
            print()
            print("→ STOP. Review manifesto-units.json by hand:")
            print(f"     {units_path.resolve()}")
            print("  Walk through every unit. Edit text, splits, or section_ids if needed.")
            print("  Then run with --stage embed to generate embeddings.")
            return

    # ── Stage: embed ──
    if args.stage in ("embed", "all"):
        print("→ Loading manifesto-units.json...")
        manifesto_units = json.loads(units_path.read_text(encoding="utf-8"))
        units = manifesto_units["units"]
        print(f"  Loaded {len(units)} units.")

        print(f"→ Generating embeddings via {EMBEDDING_MODEL}...")
        embeddings = embed_units(units)
        print(f"  ✓ Generated {embeddings.shape[0]} embeddings, {embeddings.shape[1]} dims each")

        print(f"→ Running UMAP for {len(UMAP_SEEDS)} seeds...")
        layouts = {}
        for seed in UMAP_SEEDS:
            print(f"  · seed {seed}...")
            coords = project_umap(embeddings, seed)
            layouts[str(seed)] = [[round(float(x), 4), round(float(y), 4)] for x, y in coords]

        embeddings_data = {
            "model": EMBEDDING_MODEL,
            "umap_params": UMAP_PARAMS,
            "seeds": UMAP_SEEDS,
            "unit_ids_in_order": [u["id"] for u in units],
            "layouts": layouts,
        }
        embeddings_path.write_text(
            json.dumps(embeddings_data, indent=2),
            encoding="utf-8",
        )
        print(f"  ✓ Wrote {embeddings_path.name}")

        print("→ Building resonance sources...")
        resonance = build_resonance_sources(units)
        resonance_path.write_text(
            json.dumps(resonance, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  ✓ Wrote {resonance_path.name}")
        print(f"     {len(resonance['named_sources'])} named sources, "
              f"{len(resonance['keyword_triggers'])} keyword triggers")

    print()
    print("✓ Done. Output files:")
    for f in sorted(out_dir.glob("*.json")):
        print(f"   - {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
