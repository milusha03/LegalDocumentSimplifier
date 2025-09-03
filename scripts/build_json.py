import json
from pathlib import Path

clauses = [
    # 1
    ("The lessee shall pay rent on time.",
     "The tenant must pay rent on time."),

    # 2
    ("All notices must be in writing and delivered to the other party’s registered office.",
     "All notices must be written and sent to the other party’s registered office."),

    # 3
    ("This agreement may be terminated by either party with 30 days written notice.",
     "Either party can end this agreement with 30 days’ written notice."),

    # 4
    ("The supplier warrants that the goods conform to the specifications.",
     "The supplier guarantees the goods meet the specifications."),

    # 5
    ("Neither party shall be liable for indirect or consequential damages.",
     "Neither side is responsible for indirect or consequential damages."),

    # 6
    ("Confidential information shall not be disclosed without prior consent.",
     "You must not share confidential information without prior consent."),

    # 7
    ("The parties agree to resolve disputes through arbitration in accordance with ICC rules.",
     "The parties will settle disputes by arbitration under ICC rules."),

    # 8
    ("Force majeure events include, but are not limited to, acts of God.",
     "Force majeure events include, but are not limited to, natural disasters."),

    # 9
    ("This contract is governed by the laws of the State of California.",
     "California state law governs this contract."),

    # 10
    ("Any amendments to this agreement must be in writing and signed by both parties.",
     "Any changes to this agreement must be written and signed by both parties.")
]

# Ensure the data/ folder exists
output_dir = Path("data")
output_dir.mkdir(exist_ok=True)

# Build the JSON array
data = [{"input": inp, "target": tgt} for inp, tgt in clauses]

# Write to data/clause_pairs.json
output_path = output_dir / "clause_pairs.json"
with output_path.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Written {len(data)} pairs to {output_path}")
