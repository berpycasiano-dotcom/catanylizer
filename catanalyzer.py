import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Any

import pandas as pd
import streamlit as st


# -----------------------------
# Catan "pips" (dice probability weight)
# -----------------------------
PIPS = {
    2: 1, 12: 1,
    3: 2, 11: 2,
    4: 3, 10: 3,
    5: 4, 9: 4,
    6: 5, 8: 5,
}


RESOURCES = ["wood", "brick", "sheep", "wheat", "ore", "desert"]


@dataclass(frozen=True)
class Hex:
    idx: int
    q: int
    r: int


def axial_to_pixel(q: int, r: int, size: float = 1.0) -> Tuple[float, float]:
    """
    Pointy-top hex axial -> 2D pixel center.
    """
    x = size * math.sqrt(3) * (q + r / 2)
    y = size * 3/2 * r
    return x, y


def hex_vertices(center_x: float, center_y: float, size: float = 1.0) -> List[Tuple[float, float]]:
    """
    Return 6 vertices for a pointy-top hex, starting at angle 30°.
    """
    verts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        vx = center_x + size * math.cos(angle)
        vy = center_y + size * math.sin(angle)
        verts.append((vx, vy))
    return verts


def build_standard_board() -> List[Hex]:
    """
    Standard 19-hex layout in axial coords with row lengths 3-4-5-4-3.
    We'll use r as row index and choose q ranges accordingly.
    """
    hexes: List[Hex] = []
    idx = 0

    # Rows (r) with corresponding q ranges
    # r = -2: q = 0..2  (3)
    # r = -1: q = -1..2 (4)
    # r =  0: q = -2..2 (5)
    # r =  1: q = -2..1 (4)
    # r =  2: q = -2..0 (3)
    rows = {
        -2: list(range(0, 3)),
        -1: list(range(-1, 3)),
        0: list(range(-2, 3)),
        1: list(range(-2, 2)),
        2: list(range(-2, 1)),
    }

    for r, qs in rows.items():
        for q in qs:
            hexes.append(Hex(idx=idx, q=q, r=r))
            idx += 1

    return hexes


def compute_intersections(hexes: List[Hex], size: float = 1.0, round_ndigits: int = 4) -> Dict[Tuple[float, float], List[int]]:
    """
    Build a mapping:
      vertex_coord -> list of adjacent hex indices
    """
    vertex_to_hexes: Dict[Tuple[float, float], List[int]] = {}

    for h in hexes:
        cx, cy = axial_to_pixel(h.q, h.r, size=size)
        verts = hex_vertices(cx, cy, size=size)

        for vx, vy in verts:
            key = (round(vx, round_ndigits), round(vy, round_ndigits))
            vertex_to_hexes.setdefault(key, [])
            if h.idx not in vertex_to_hexes[key]:
                vertex_to_hexes[key].append(h.idx)

    # Keep only valid intersections (2 or 3 adjacent hexes)
    vertex_to_hexes = {k: v for k, v in vertex_to_hexes.items() if 1 < len(v) <= 3}
    return vertex_to_hexes


def score_intersection(adj_hex_indices: List[int], hex_data: Dict[int, Dict[str, Any]], diversity_bonus: float = 0.5) -> Dict[str, Any]:
    """
    Score = sum(pips(number)) + diversity_bonus*(#distinct_resources - 1)
    Desert contributes 0 pips and does not count for diversity.
    """
    total_pips = 0
    resources = []
    details = []

    for i in adj_hex_indices:
        res = hex_data[i]["resource"]
        num = hex_data[i]["number"]
        pip = PIPS.get(num, 0) if res != "desert" else 0

        if res != "desert":
            resources.append(res)

        details.append(f"{res} {num if num is not None else ''}".strip())
        total_pips += pip

    distinct = len(set(resources))
    diversity = diversity_bonus * max(0, distinct - 1)
    score = total_pips + diversity

    return {
        "score": score,
        "pips_sum": total_pips,
        "diversity_bonus": diversity,
        "adjacent": ", ".join(details),
        "distinct_resources": distinct,
        "hex_count": len(adj_hex_indices),
    }


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Catanalyzer", layout="wide")
st.title("Catanalyzer — Settlement Spot Scorer (MVP)")

st.markdown(
    """
This MVP scores settlement intersections using:
- **Pips (dice probability weights)** for adjacent numbers
- **Resource diversity bonus** to reward variety

You enter the **19 hex tiles** (resource + number), and the app ranks the best intersections automatically.
"""
)

hexes = build_standard_board()
vertex_map = compute_intersections(hexes, size=1.0, round_ndigits=4)

st.sidebar.header("Scoring Controls")
div_bonus = st.sidebar.slider("Diversity bonus per extra distinct resource", 0.0, 2.0, 0.5, 0.1)
top_n = st.sidebar.slider("Show Top N intersections", 5, 30, 15, 1)

st.subheader("1) Enter board tiles (19 hexes)")

# Provide a reasonable default template (classic resources distribution not enforced in MVP)
# User can overwrite.
default_resources = (["wood"] * 4) + (["brick"] * 3) + (["sheep"] * 4) + (["wheat"] * 4) + (["ore"] * 3) + (["desert"] * 1)
default_numbers = [5, 2, 6, 3, 8, 10, 9, 12, 11, 4, 8, 10, 9, 4, 5, 6, 3, 11, None]

# Initialize session state for edits
if "hex_table" not in st.session_state:
    df_init = pd.DataFrame({
        "hex_idx": [h.idx for h in hexes],
        "resource": default_resources[:19],
        "number": default_numbers[:19],
    })
    st.session_state.hex_table = df_init

df = st.session_state.hex_table.copy()

st.caption("Tip: desert should have number = blank (None). Numbers outside {2..12} are treated as 0 pips.")

edited = st.data_editor(
    df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "hex_idx": st.column_config.NumberColumn("hex_idx", disabled=True),
        "resource": st.column_config.SelectboxColumn("resource", options=RESOURCES),
        "number": st.column_config.NumberColumn("number", help="Use 2–12. Leave blank for desert."),
    },
)

st.session_state.hex_table = edited

# Validate and build hex_data dict
hex_data: Dict[int, Dict[str, Any]] = {}
invalid_msgs = []

for row in edited.to_dict(orient="records"):
    idx = int(row["hex_idx"])
    res = row["resource"]
    num = row["number"]

    # Convert NaN to None
    if pd.isna(num):
        num = None
    else:
        try:
            num = int(num)
        except Exception:
            num = None

    if res == "desert":
        num = None
    else:
        if num is None or num < 2 or num > 12:
            invalid_msgs.append(f"Hex {idx}: non-desert tile needs a valid number 2–12.")

    hex_data[idx] = {"resource": res, "number": num}

if invalid_msgs:
    st.warning("Fix these input issues for accurate scoring:\n- " + "\n- ".join(invalid_msgs))

st.subheader("2) Ranked intersections")

rows = []
for vertex, adj_hex_indices in vertex_map.items():
    s = score_intersection(adj_hex_indices, hex_data, diversity_bonus=div_bonus)
    rows.append({
        "intersection_id": f"V({vertex[0]}, {vertex[1]})",
        "score": round(s["score"], 2),
        "pips_sum": s["pips_sum"],
        "diversity_bonus": round(s["diversity_bonus"], 2),
        "distinct_resources": s["distinct_resources"],
        "hex_count": s["hex_count"],
        "adjacent_hexes": s["adjacent"],
    })

out = pd.DataFrame(rows).sort_values(["score", "pips_sum", "distinct_resources"], ascending=False).reset_index(drop=True)

st.dataframe(out.head(top_n), use_container_width=True)

st.markdown("### Interpretation tips")
st.markdown(
    """
- **Pips sum** captures expected production (6/8 are strongest).
- **Diversity bonus** reduces the risk of being blocked by one scarce resource.
- Intersections with **3 adjacent hexes** are usually stronger than edge (2-hex) spots.
"""
)
