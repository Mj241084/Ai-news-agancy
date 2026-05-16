from __future__ import annotations

import re
from html import escape
from urllib.parse import urlsplit

import bleach
import markdown

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
VIDEO_EXTS = (".mp4", ".webm", ".ogv")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".ogg")

_MIME_BY_EXT = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".ogv": "video/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
}

ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS).union(
    {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "pre",
        "code",
        "hr",
        "br",
        "blockquote",
        "ul",
        "ol",
        "li",
        "strong",
        "em",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "img",

        # Inline media (direct links)
        "figure",
        "figcaption",
        "video",
        "audio",
        "source",
    }
)

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel", "target"],
    # NOTE: width/height help reduce CLS; loading/decoding improve CWV.
    "img": ["src", "alt", "title", "loading", "decoding", "width", "height"],
    "code": ["class"],
    "th": ["colspan", "rowspan"],
    "td": ["colspan", "rowspan"],

    # Inline media attrs (kept intentionally small for security)
    "video": ["controls", "preload", "poster", "playsinline", "width", "height"],
    "audio": ["controls", "preload"],
    "source": ["src", "type"],
}


def _is_http_url(s: str) -> bool:
    try:
        u = urlsplit((s or "").strip())
        return u.scheme in ("http", "https") and bool(u.netloc)
    except Exception:
        return False


def _path_lower(url: str) -> str:
    return (urlsplit(url).path or "").lower()


def _parse_kv_parts(parts: list[str]) -> dict[str, str]:
    """Parse key=value chunks separated by `|`."""
    out: dict[str, str] = {}
    for p in parts:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k and v:
            out[k] = v
    return out


_ONLY_URL_LINE_RE = re.compile(r"^https?://\S+$", flags=re.IGNORECASE)


def _auto_embed_media(md_text: str) -> str:
    """
    Convert *standalone* direct media links to safe embeds.

    Supported line formats:
      URL
      URL | alt=... | caption=...
      URL | poster=... | caption=...

    Notes:
      - Only triggers when the line is just a URL (plus optional `| key=value`).
      - Keeps page performance sane: video/audio use preload="none".
    """
    lines = (md_text or "").splitlines()
    out: list[str] = []

    in_fence = False
    fence_delim: str | None = None

    for line in lines:
        raw = (line or "").strip()

        # Don't touch fenced / indented code blocks.
        stripped = (line or "").lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            delim = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_delim = delim
            elif fence_delim == delim:
                in_fence = False
                fence_delim = None
            out.append(line)
            continue

        if in_fence or (line.startswith("    ") or line.startswith("\t")):
            out.append(line)
            continue

        if not raw:
            out.append(line)
            continue

        parts = [p.strip() for p in raw.split("|")]
        url = parts[0]
        opts = _parse_kv_parts(parts[1:])

        # Trigger only for clean/standalone URLs
        if not _ONLY_URL_LINE_RE.match(url) or not _is_http_url(url):
            out.append(line)
            continue

        path = _path_lower(url)
        caption = escape((opts.get("caption") or "").strip())
        alt = escape((opts.get("alt") or "").strip())
        poster = (opts.get("poster") or "").strip()
        width = (opts.get("w") or opts.get("width") or "").strip()
        height = (opts.get("h") or opts.get("height") or "").strip()

        def _safe_int(v: str) -> str:
            try:
                n = int(str(v).strip())
                if 1 <= n <= 10000:
                    return str(n)
            except Exception:
                pass
            return ""

        w_attr = _safe_int(width)
        h_attr = _safe_int(height)
        size_attrs = ""
        if w_attr:
            size_attrs += f' width="{w_attr}"'
        if h_attr:
            size_attrs += f' height="{h_attr}"'


        if any(path.endswith(ext) for ext in IMAGE_EXTS):
            # Use <figure> when we need caption and/or explicit dimensions (for CLS).
            if caption or size_attrs:
                figcap = f"<figcaption>{caption}</figcaption>" if caption else ""
                html = (
                    "\n\n<figure>"
                    f'<img src="{escape(url)}" alt="{alt}" loading="lazy" decoding="async"{size_attrs}>'
                    f"{figcap}"
                    "</figure>\n\n"
                )
                out.append(html)
            else:
                # Keep it as markdown to preserve normal rendering.
                out.append(f"![{alt}]({url})")
            continue

        if any(path.endswith(ext) for ext in VIDEO_EXTS):
            ext = next((e for e in VIDEO_EXTS if path.endswith(e)), ".mp4")
            mime = _MIME_BY_EXT.get(ext, "video/mp4")
            poster_attr = f' poster="{escape(poster)}"' if poster and _is_http_url(poster) else ""

            html = (
                "\n\n<figure>"
                f"<video controls preload=\"none\" playsinline{poster_attr}{size_attrs}>"
                f'<source src="{escape(url)}" type="{escape(mime)}">'
                "</video>"
                f"{f'<figcaption>{caption}</figcaption>' if caption else ''}"
                "</figure>\n\n"
            )
            out.append(html)
            continue

        if any(path.endswith(ext) for ext in AUDIO_EXTS):
            ext = next((e for e in AUDIO_EXTS if path.endswith(e)), ".mp3")
            mime = _MIME_BY_EXT.get(ext, "audio/mpeg")

            html = (
                "\n\n<figure>"
                "<audio controls preload=\"none\">"
                f'<source src="{escape(url)}" type="{escape(mime)}">'
                "</audio>"
                f"{f'<figcaption>{caption}</figcaption>' if caption else ''}"
                "</figure>\n\n"
            )
            out.append(html)
            continue

        out.append(line)

    return "\n".join(out)


def render_markdown_safe(md_text: str) -> str:
    md_text = _auto_embed_media(md_text)

    raw_html = markdown.markdown(
        md_text or "",
        extensions=["extra", "sane_lists", "tables", "fenced_code", "nl2br"],
        output_format="html5",
    )

    cleaned = bleach.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
    return bleach.linkify(cleaned)
