"""LaTeX 公式渲染为 PNG（matplotlib mathtext，无需本地 TeX 安装）。

译文可能含大模型恢复的 $...$ / $$...$$ 公式；卡片在完成时把公式换成
渲染图片，呈现与论文一致的上下标视觉形式。不支持的语法保留原文。
"""
import html
import re
import threading

_FORMULA_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$|(?<!\\)\$(.+?)(?<!\\)\$", re.S)
_CURRENCY_AMOUNT_RE = re.compile(r"\s*\d+(?:[.,]\d+)?\s*")
_MAX_CACHE_ENTRIES = 256

_png_cache: dict[tuple[str, str], bytes] = {}
_cache_lock = threading.Lock()


def render_formula_png(latex: str, color: str = "#171C26") -> bytes | None:
    """把公式渲染成透明背景 PNG；失败返回 None（调用方保留原文）。"""
    key = (latex, color)
    with _cache_lock:
        cached = _png_cache.get(key)
    if cached is not None:
        return cached
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        fig = Figure(dpi=100)
        FigureCanvasAgg(fig)
        fig.text(0, 0, f"${latex}$", fontsize=12, color=color)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0.03)
        png = buf.getvalue()
    except Exception:
        return None
    with _cache_lock:
        _png_cache[key] = png
        while len(_png_cache) > _MAX_CACHE_ENTRIES:
            del _png_cache[next(iter(_png_cache))]
    return png


def build_rich_html(text: str, color: str = "#171C26") -> tuple[str, dict[str, bytes]] | None:
    """按公式切分文本，生成卡片 HTML 与图片资源表；无公式返回 None。"""
    parts: list[str] = []
    images: dict[str, bytes] = {}
    pos = 0
    for m in _FORMULA_RE.finditer(text):
        latex = m.group(1) or m.group(2)
        is_inline = m.group(1) is None
        # `$5, $10`、`$5-$10` 等金额包含两个美元符号，不能当成公式。
        if is_inline and (
            _CURRENCY_AMOUNT_RE.fullmatch(latex)
            or (latex[:1].isdigit() and text[m.end():m.end() + 1].isdigit())
        ):
            continue
        if m.start() > pos:
            parts.append(html.escape(text[pos:m.start()]).replace("\n", "<br>"))
        png = render_formula_png(latex, color)
        if png is None:
            parts.append(html.escape(m.group(0)))
        else:
            name = f"formula{len(images)}"
            images[name] = png
            parts.append(f'<img src="{name}">')
        pos = m.end()
    if not images:
        return None
    if pos < len(text):
        parts.append(html.escape(text[pos:]).replace("\n", "<br>"))
    return "".join(parts), images


def warmup():
    """启动时后台预热 matplotlib 渲染环境，避免首次渲染公式卡顿。"""
    render_formula_png("x_i")
