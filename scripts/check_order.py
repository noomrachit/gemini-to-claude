#!/usr/bin/env python3
"""
Auto-validator for @pora7307 work orders in `orders/<clip_code>.md`.
Generates `replies/<clip_code>.md` with APPROVED or NEEDS_REVISION status
and ready-to-use video generation prompts when approved.
"""

import re
from pathlib import Path
from typing import Any

ORDERS_DIR = Path("orders")
REPLIES_DIR = Path("replies")
OWNER_NOTES_DIR = Path("owner-notes")

MIN_SCENE_SECONDS = 3  # guide.md: ฉากละ 3–6 วินาที
MAX_SCENE_SECONDS = 6

FORBIDDEN_WORDS = [
    "ดีที่สุด",
    "ถูกที่สุด",
    "อันดับ 1",
    "รับประกัน 100%",
    "หายขาด",
    "เห็นผลทันที",
    "ด่วนก่อนหมด",
]

BURNOUT_KEYWORDS = [
    "หมดแรง",
    "เหนื่อยล้า",
    "ใจหนัก",
    "ไม่ไหวแล้ว",
    "ท้อแท้",
    "สิ้นหวัง",
    "อยากหายไป",
]

VISUAL_RISK_PATTERNS = [
    (r"\b(?:with\s+text|text\s+overlay|subtitles?|caption\s+in\s+video|signboard|billboard)\b", "อาจมีตัวหนังสือในภาพ/วิดีโอ"),
    (r"\b(?:brand\s+logo|nike|apple\s+logo|iphone\s+logo|gucci|starbucks)\b", "อาจมีโลโก้แบรนด์"),
    (r"\b(?:celebrity|famous\s+actor|close-up\s+face|looking\s+at\s+camera\s+portrait)\b", "อาจมีหน้าคนจริงที่ระบุตัวได้หรือตัวละครดัง"),
]


def parse_work_order(md_text: str, fallback_code: str) -> dict[str, Any]:
    clip_match = re.search(r"รหัสคลิป:\s*([^\n\r]+)", md_text)
    clip_code = clip_match.group(1).strip() if clip_match else fallback_code

    scenes: list[dict[str, Any]] = []

    block_pattern = re.compile(
        r"ฉาก\s*(\d+)\s*\((\d+)\s*วินาที\).*?"
        r"พรอมต์ภาพ:\s*(.+?)\n"
        r"บทพากย์:\s*(.+?)(?=\nฉาก\s*\d+|\Z)",
        re.DOTALL,
    )
    for m in block_pattern.finditer(md_text):
        scenes.append({
            "scene_no": int(m.group(1)),
            "duration": int(m.group(2)),
            "visual_prompt": " ".join(m.group(3).split()),
            "voiceover_th": " ".join(m.group(4).split()),
            "raw_block": m.group(0),
        })

    if not scenes:
        for line in md_text.splitlines():
            line_s = line.strip()
            if line_s.startswith("|"):
                parts = [p.strip() for p in line_s.strip("|").split("|")]
                if len(parts) >= 4 and parts[0].isdigit() and parts[1].isdigit():
                    scenes.append({
                        "scene_no": int(parts[0]),
                        "duration": int(parts[1]),
                        "visual_prompt": parts[2],
                        "voiceover_th": parts[3],
                        "screen_text": parts[4] if len(parts) > 4 else "",
                        "raw_block": line_s,
                    })

    return {"clip_code": clip_code, "scenes": scenes, "raw": md_text}


def validate_work_order(wo: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    scenes = wo["scenes"]
    raw_text = wo["raw"]

    if not scenes:
        issues.append("ไม่พบตารางฉากหรือรูปแบบ `ฉาก N (X วินาที)` ในใบสั่งงาน")
        return issues

    total_dur = 0
    for sc in scenes:
        s_no = sc["scene_no"]
        dur = sc["duration"]
        vp = sc["visual_prompt"]

        if not (MIN_SCENE_SECONDS <= dur <= MAX_SCENE_SECONDS):
            issues.append(f"ฉาก {s_no}: ความยาว {dur} วินาที ไม่ตรงกติกา (ต้องอยู่ระหว่าง 3–6 วินาที)")
        total_dur += dur

        for pat, reason in VISUAL_RISK_PATTERNS:
            if re.search(pat, vp, re.IGNORECASE) and not re.search(r"no\s+(text|logo|face)", vp, re.IGNORECASE):
                issues.append(f"ฉาก {s_no}: พรอมต์ภาพ {reason}")

    if not (15 <= total_dur <= 30):
        issues.append(f"ความยาวรวม {total_dur} วินาที อยู่นอกเกณฑ์ 15-30 วินาที")

    for word in FORBIDDEN_WORDS:
        if word in raw_text:
            issues.append(f"พบคำต้องห้ามในเนื้อหา: `{word}`")

    if any(kw in raw_text for kw in BURNOUT_KEYWORDS):
        last_scene = scenes[-1]
        last_text = " ".join([
            last_scene.get("voiceover_th", ""),
            last_scene.get("screen_text", ""),
            last_scene.get("raw_block", ""),
        ])
        owner_text = wo.get("owner_text", "")
        if "1323" not in last_text and "1323" not in owner_text:
            tail_idx = raw_text.rfind(f"ฉาก {last_scene['scene_no']}")
            tail_text = raw_text[tail_idx:] if tail_idx != -1 else last_text
            if "1323" not in tail_text:
                issues.append(f"ฉาก {last_scene['scene_no']} (ฉากสุดท้าย): เนื้อหาแตะเรื่องหมดแรง/ใจหนัก แต่ยังไม่มีสายด่วนสุขภาพจิต `1323`")

    return issues


def build_reply_markdown(wo: dict[str, Any], issues: list[str]) -> str:
    clip_code = wo["clip_code"]
    scenes = wo["scenes"]
    total_dur = sum(s["duration"] for s in scenes)

    if issues:
        lines = [
            f"# ผลตรวจใบสั่งงาน: {clip_code}",
            "",
            "**สถานะ:** `NEEDS_REVISION`",
            "",
            "## รายการที่ต้องแก้ไข (กรุณาแก้ในต้นฉบับโดยเดชา)",
            "",
        ]
        for item in issues:
            lines.append(f"- {item}")
        lines.append("")
        return "\n".join(lines)

    lines = [
        f"# ผลตรวจใบสั่งงาน: {clip_code}",
        "",
        "**สถานะ:** `APPROVED`",
        f"**ความยาวรวม:** {total_dur} วินาที ({len(scenes)} ฉาก)",
        "",
        "## พรอมต์สร้างวิดีโอพร้อมใช้ (คัดลอกไปกดสร้างได้ทันที)",
        "",
    ]

    for sc in scenes:
        # The order's visual prompt already carries the style and "no text/logo/face"
        # rules, so only add the aspect ratio if it is missing, plus the duration.
        vp = sc["visual_prompt"].rstrip(".")
        if "9:16" not in vp:
            vp = f"Vertical 9:16. {vp}"
        ready_prompt = f"{vp}. {sc['duration']} seconds."
        lines.extend([
            f"### ฉาก {sc['scene_no']} ({sc['duration']} วินาที)",
            "**พรอมต์วิดีโอ:**",
            "```text",
            ready_prompt,
            "```",
            f"**บทพากย์ (ผู้หญิง นุ่ม อบอุ่น พูดช้า):** {sc['voiceover_th']}",
            "",
        ])

    return "\n".join(lines)


def load_owner_notes(clip_code: str) -> str:
    """Return owner-notes text for this clip (matched by clip code in the file)."""
    if not OWNER_NOTES_DIR.exists():
        return ""
    texts = []
    for path in sorted(OWNER_NOTES_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if clip_code and clip_code in text:
            texts.append(text)
    return "\n".join(texts)


def main() -> None:
    if not ORDERS_DIR.exists():
        print("No orders/ directory found.")
        return

    REPLIES_DIR.mkdir(parents=True, exist_ok=True)
    order_files = sorted(ORDERS_DIR.glob("*.md"))
    if not order_files:
        print("No order files found in orders/.")
        return

    for order_path in order_files:
        md_text = order_path.read_text(encoding="utf-8")
        wo = parse_work_order(md_text, order_path.stem)
        wo["owner_text"] = load_owner_notes(wo["clip_code"])
        issues = validate_work_order(wo)
        reply_md = build_reply_markdown(wo, issues)

        reply_path = REPLIES_DIR / order_path.name
        reply_path.write_text(reply_md, encoding="utf-8")
        status = "NEEDS_REVISION" if issues else "APPROVED"
        print(f"[{status}] {order_path} -> {reply_path}")


if __name__ == "__main__":
    main()
