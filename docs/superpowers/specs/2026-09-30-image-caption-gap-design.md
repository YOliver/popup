# 图片与图注间距过大 — 设计文档

- 日期：2026-09-30
- 状态：已实现
- 关联版本：v1.7.1

## 1. 背景与问题

Popup 用 python-markdown 把 Markdown 转成 HTML，再经 `wrap_html()` 包裹后由 `QTextBrowser.setHtml()` 显示。`wrap_html()` 的 CSS 中定义了 `body { line-height: 1.6; }`，用于放大正文行距、提升可读性。

但 Qt 富文本引擎在计算「含图片的行」的行高时，会把 `line-height` 倍数作用于图片本身的高度：一张 376px 高的图片，其所在行被放大到约 590px，多出的约 225px 全部落在图片下方，导致图片与其后的图注（`*图1-1 …*`）之间出现一大段空白。

实测（真实渲染管线，`setPageSize` 强制布局后读取 `blockBoundingRect`）：

| 场景 | 图片 block 底 → 图注 block 顶间距 |
|------|----------------------------------|
| `body { line-height: 1.6 }` | 约 237px（复现问题） |
| `body { line-height: 1.0 }` | 12px（正常段落间距） |
| 图片段落单独 `line-height:100%` | 12px（正常） |

图片文件本身不是原因：`fig1-1.png` 为 658×376，底部空白仅 19px。

## 2. 目标与非目标

### 目标

- 让「内容仅为一或多张图片（可带前置锚点）的段落」不受 `body line-height:1.6` 影响，图片紧贴下一段（图注），恢复正常的约 12px 段落间距。
- 不影响正文段落的行距（正文仍保持 1.6 倍行距）。
- 不影响图文混排段落、目录边栏、滚动同步锚点映射等既有功能。

### 非目标（YAGNI）

- 不改动全局 `line-height`。
- 不做图片自动裁剪、等比缩放、居中、点击放大等增强。
- 不处理「图片 + 文字在同一段落内」的行距（Qt 对这类行的处理本就复杂，本次问题仅出现在纯图片段落）。
- 不处理列表项内的图片（`<li><img …/></li>` 不在 `<p>` 内，且列表内图片在本书笔记场景中罕见，YAGNI）。

## 3. 方案概述

在渲染管线中新增一个后处理步骤：对「仅含锚点空标签 + 一张或多张 `<img>` 的 `<p>`」段落注入 `style="line-height:100%"`，用 `line-height:100%` 覆盖继承自 `body` 的 1.6 倍，使图片行高回归图片实际高度。已实测有效且改动最小。

## 4. 详细设计

### 4.1 改动点

**文件：`md_viewer.py`**

1. 新增静态方法 `_fix_image_line_height(html)`，与现有 `_style_blockquotes`、`_apply_indent` 同风格（正则字符串替换，不引入依赖）：

```python
@staticmethod
def _fix_image_line_height(html: str) -> str:
    """给「仅含图片（可带前置锚点）的段落」注入 line-height:100%。

    Qt 会把 body 的 line-height 倍数作用于图片行，导致图片行高被放大 1.6 倍，
    图片下方出现大段空白。对纯图片段落覆盖为 100%，恢复图片实际行高。
    python-markdown 输出格式固定为 <p><a id="popup-anchor-N"></a><img .../></p>；
    同一段落可能含多张图片，nl2br 扩展会把段落内软换行转成 <br />，
    故用 (?:<img [^>]*/>\s*(?:<br />\s*)?)+ 匹配一张或多张图片（其间可夹 <br />）。
    """
    pattern = r'<p>((?:<a id="popup-anchor-\d+"></a>)*(?:<img [^>]*/>\s*(?:<br />\s*)?)+)</p>'
    return re.sub(pattern, r'<p style="line-height:100%">\1</p>', html)
```

2. 在 `reload_file()` 的 `_apply_indent(html_body, em_px)` 之后（`md_viewer.py:850` 附近）调用：

```python
html_body = self._apply_indent(html_body, em_px)
html_body = self._fix_image_line_height(html_body)
html_body = self._style_blockquotes(html_body)
```

### 4.2 关键细节

- 正则只匹配「段落内容完全由 `<a id="popup-anchor-N"></a>` 空锚点 + 一个或多个 `<img>` 组成」的 `<p>`。普通图文混排段落（img 前后有文字）不会被命中，行为不变。
- `popup-anchor-N` 是 `_inject_anchors` 注入的固定前缀（见 `md_viewer.py`），正则与之保持一致；`\d+` 匹配编号。
- 锚点标签在替换中原样保留，`_build_anchor_map` 依赖的 `popup-anchor-N` 属性不受影响，滚动同步锚点映射不破坏。
- 该步骤放在 `_style_blockquotes` 之前：`_style_blockquotes` 只处理 `<blockquote>`，与 `<p>` 图片段落无交集，顺序无耦合；放在 `_apply_indent` 之后是因为 `_apply_indent` 的占位标记 `<i data-indent>` 不会出现在纯图片段落内，两者互不影响。
- `line-height:100%` 是 Qt 富文本引擎可正确解析的单位形式（已实测；`em` 单位在 Qt 中不可靠，`text-indent` 处已有此经验教训）。

### 4.3 数据流

```
Markdown 源 → _inject_anchors → _preserve_indent → md.convert()
                                                      ↓
                                      <p><a id="popup-anchor-89"></a><img .../></p>
                                                      ↓
                              _apply_indent（对段首缩进占位处理）
                                                      ↓
                              _fix_image_line_height（纯图片段落注入 line-height:100%）
                                                      ↓
                              _style_blockquotes → wrap_html → setHtml
```

## 5. 边界情况

| 场景 | 预期行为 |
|------|---------|
| 纯图片段落（无锚点） | 注入 `line-height:100%`，图片紧贴图注 |
| 纯图片段落（带锚点） | 注入 `line-height:100%`，锚点保留 |
| 带段首缩进的图片段落（`_apply_indent` 注入 `text-indent`） | 注入并合并为 `text-indent:...;line-height:100%` |
| 图文混排段落（`<p>文字 <img> 文字</p>`） | 不注入，行为不变 |
| 图片 alt 含特殊字符/中文 | 正则 `[^>]*` 覆盖 alt 属性值，正常匹配（alt 中的 `>` 会被 markdown 转义为 `&gt;`，不误切） |
| 同一段落多张图片（`![](a.png) ![](b.png)`） | 整段一次注入，各图间距均恢复 |
| 软换行多张图片（`![](a.png)` 换行 `![](b.png)`，nl2br 生成 `<br />`） | 整段一次注入，各图间距均恢复 |
| 连续多个图片段落 | 每段各自注入 |
| 列表项内图片（`<li><img/></li>`） | 不注入（非目标） |
| 图片被链接包裹（`[![alt](src)](url)`） | 不注入（已知限制，保留原间距） |
| 图片与图注无空行同段（`![](x.png)` 换行 `*图注*`，nl2br 生成 `<br />`） | 不注入（非目标） |
| 滚动同步锚点映射 | `popup-anchor-N` 标签原样保留，映射不受影响 |

## 6. 测试计划

在 `tests/` 新增 `test_image_line_height.py`（unittest，纯字符串断言，无需 QApplication/offscreen，可稳定运行）：

1. 纯图片段落（无锚点）被注入 `line-height:100%`。
2. 带 `popup-anchor-N` 锚点的图片段落被注入，且锚点标签完整保留。
3. 图文混排段落不被改动。
4. 同一段落多张图片（`![](a.png) ![](b.png)`）被注入 `line-height:100%`。
5. 软换行多张图片（nl2br 生成 `<br />`）被注入 `line-height:100%`。
6. 通过完整 `markdown` 管线（`![alt](x.png)` 源文本）产出含 `line-height:100%` 的图片段落。

手动冒烟：构建后打开《失去的二十年》等含图片的文档，确认图片与图注间距恢复正常、目录跳转与滚动同步正常。

## 7. 影响分析

- 改动集中在 `md_viewer.py` 一个新增方法 + 一处调用，不触碰滚动同步、目录、搜索、托盘等其他模块。
- 不引入新依赖。
- 仅影响纯图片段落的行高，正文行距保持不变。
