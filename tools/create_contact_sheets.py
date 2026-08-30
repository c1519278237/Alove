from pathlib import Path
import sys

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / ".codex_deps"))

from PIL import Image, ImageDraw, ImageFont


def main():
    render_name = sys.argv[1] if len(sys.argv) > 1 else "render-v1"
    source = WORKSPACE / "qa" / render_name
    output = source / "contact-sheets"
    output.mkdir(parents=True, exist_ok=True)
    pages = sorted(source.glob("page-*.png"))
    font = ImageFont.truetype(r"C:\Windows\Fonts\NotoSansSC-VF.ttf", 28)
    per_sheet = 6
    cols, rows = 3, 2
    thumb_w, thumb_h = 780, 1010
    gutter = 26
    label_h = 48
    for start in range(0, len(pages), per_sheet):
        chunk = pages[start:start + per_sheet]
        canvas = Image.new(
            "RGB",
            (cols * thumb_w + (cols + 1) * gutter, rows * (thumb_h + label_h) + (rows + 1) * gutter),
            "#CDD5DB",
        )
        draw = ImageDraw.Draw(canvas)
        for idx, page_path in enumerate(chunk):
            page = Image.open(page_path).convert("RGB")
            page.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            col = idx % cols
            row = idx // cols
            x = gutter + col * (thumb_w + gutter) + (thumb_w - page.width) // 2
            y = gutter + row * (thumb_h + label_h)
            canvas.paste(page, (x, y))
            label = f"第 {start + idx + 1} 页"
            bbox = draw.textbbox((0, 0), label, font=font)
            draw.text(
                (gutter + col * (thumb_w + gutter) + (thumb_w - (bbox[2] - bbox[0])) / 2, y + thumb_h + 7),
                label,
                font=font,
                fill="#17324D",
            )
        sheet_no = start // per_sheet + 1
        canvas.save(output / f"sheet-{sheet_no:02d}.png", optimize=True)
    print(f"created {((len(pages)-1)//per_sheet)+1} sheets for {len(pages)} pages")


if __name__ == "__main__":
    main()
