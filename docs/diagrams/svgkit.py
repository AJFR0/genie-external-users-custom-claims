"""A tiny SVG builder for the guide diagrams: boxes, arrows, numbered badges. Safe for rsvg and WeasyPrint."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

FONT = "Helvetica, Arial, sans-serif"
MONO = "Menlo, Consolas, monospace"
C = {"ink": "#1f2933", "muted": "#52606d", "line": "#9aa5b1", "soft": "#d9e2ec", "panel": "#f5f7fa", "white": "#ffffff",
     "claim": "#2f6fde", "claim_bg": "#eaf1fd", "ok": "#1f9d55", "ok_bg": "#e6f6ed", "deny": "#d64545", "deny_bg": "#fdecec",
     "mask": "#b7791f", "mask_bg": "#fdf4e3", "genie": "#7b5bd6", "genie_bg": "#f1edfb"}


def col(name: str) -> str:
    return C.get(name, name)


@dataclass
class Svg:
    width: int
    height: int
    parts: list = field(default_factory=list)

    def rect(self, x, y, w, h, *, fill="white", stroke="soft", rx=10, width=1.5, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{col(fill)}" '
                          f'stroke="{col(stroke)}" stroke-width="{width}"{d}/>')

    def text(self, x, y, s, *, size=14, color="ink", weight="normal", anchor="start", mono=False):
        space = ' xml:space="preserve"' if mono else ""
        self.parts.append(f'<text x="{x}" y="{y}" font-family="{MONO if mono else FONT}" font-size="{size}" '
                          f'fill="{col(color)}" font-weight="{weight}" text-anchor="{anchor}"{space}>{escape(s)}</text>')

    def lines(self, x, y, items, *, size=13, gap=1.4, **kw):
        for i, s in enumerate(items):
            self.text(x, y + i * size * gap, s, size=size, **kw)

    def box(self, x, y, w, h, title, body=(), *, fill="white", stroke="soft", title_color="ink", size=15, body_size=12.5,
            mono_body=False, center=False):
        self.rect(x, y, w, h, fill=fill, stroke=stroke)
        tx, anchor = (x + w / 2, "middle") if center else (x + 14, "start")
        self.text(tx, y + 26, title, size=size, weight="bold", color=title_color, anchor=anchor)
        self.lines(tx, y + 48, body, size=body_size, color="muted", anchor=anchor, mono=mono_body)

    def arrow(self, points, *, color="line", width=2, dash=None, label=None, label_pos=None, head=True):
        pts = " ".join(f"{x},{y}" for x, y in points)
        d = f' stroke-dasharray="{dash}"' if dash else ""
        m = f' marker-end="url(#arrow-{color})"' if head else ""
        self.parts.append(f'<polyline points="{pts}" fill="none" stroke="{col(color)}" stroke-width="{width}"{d}{m}/>')
        if label:
            lx, ly = label_pos or ((points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2 - 8)
            self.text(lx, ly, label, size=12, color=color, anchor="middle")

    def badge(self, x, y, n, *, color="claim", r=13):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col(color)}"/>')
        self.text(x, y + 4.5, str(n), size=13, color="white", weight="bold", anchor="middle")

    def pill(self, x, y, label, *, color="claim", bg="white", size=12) -> float:
        w = 16 + len(label) * size * 0.56
        self.rect(x, y, w, size + 12, fill=bg, stroke=color, rx=(size + 12) / 2, width=1.2)
        self.text(x + w / 2, y + size + 3, label, size=size, color=color, anchor="middle")
        return w

    def render(self) -> str:
        markers = "".join(f'<marker id="arrow-{n}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
                          f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{v}"/></marker>' for n, v in C.items())
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
                f'viewBox="0 0 {self.width} {self.height}" role="img"><defs>{markers}</defs>'
                f'<rect width="100%" height="100%" fill="#ffffff"/>' + "".join(self.parts) + "</svg>")

    def save(self, path: Path) -> None:
        path.write_text(self.render(), encoding="utf-8")
