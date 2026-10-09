# 引用块空灰条修复 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除引用块内「空灰条」——修复 `_inject_anchors` 给空引用行注锚导致的段间空行盒，以及 nl2br 产生的段落末尾悬空 `<br />` 空行盒。

**Architecture:** 修复 A 让 `_inject_anchors` 跳过空引用行（恢复段落分隔）；修复 B 新增 HTML 后处理删除段落末尾悬空 `<br />`。

**Tech Stack:** Python 3.8+ / PySide6 (Qt6)

## Global Constraints

- 业务代码只改 `md_viewer.py`；测试加在 `tests/test_inject_anchors.py` 与 `tests/test_quote_rendering.py`。不得改动其他文件。
- 不新增任何第三方依赖。
- 代码注释与 git commit message 一律中文。
- 版本号保持 `"1.7.5"`（未发布，同一版本内迭代，不改）。
- 不改 `_inject_anchors` 的标题/列表/段落等其他注入逻辑，不改背景色/左竖线样式。

---

### Task 1: 修复 A —— `_inject_anchors` 跳过空引用行

**Files:**
- Modify: `md_viewer.py`（`_inject_anchors` 的引用分支，约 1114-1117 行）
- Test: `tests/test_inject_anchors.py`（新增一个测试方法）

**Interfaces:**
- Consumes: 无
- Produces: 无

- [ ] **Step 1: 写失败的测试**

在 `tests/test_inject_anchors.py` 新增：

```python
    def test_blank_quote_lines_not_anchored(self):
        src = "> 文字\n>\n>　\n> 更多"
        out = MarkdownViewer._inject_anchors(src)
        lines = out.split("\n")
        self.assertIn("popup-anchor-0", lines[0])
        self.assertEqual(lines[1], ">")       # 空引用行不注锚，原样保留
        self.assertEqual(lines[2], ">　")     # 仅全角空格的引用行也不注锚
        self.assertIn("popup-anchor-3", lines[3])
```

（若该文件是 unittest 风格且已有 `MarkdownViewer` 导入，直接加到对应 TestCase 类里；方法名保持 `test_` 前缀。）

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_inject_anchors.py::*test_blank_quote_lines_not_anchored -v`
Expected: FAIL（当前空引用行被注锚，`lines[1]` 为 `><a id="popup-anchor-1"></a>` 而非 `>`）

- [ ] **Step 3: 改代码**

在 `md_viewer.py` 的 `_inject_anchors` 中，把（约 1114-1117 行）：

```python
            mq = quote_re.match(line)
            if mq:
                out.append(f'{mq.group(1)}{anchor}{mq.group(2)}')
                continue
```

改为：

```python
            mq = quote_re.match(line)
            if mq:
                if mq.group(2).strip('\u3000 \t'):
                    out.append(f'{mq.group(1)}{anchor}{mq.group(2)}')
                else:
                    out.append(line)  # 空引用行不注锚，保持段落分隔符
                continue
```

改之前先 `Read` 确认原文。

- [ ] **Step 4: 运行测试确认通过 + 回归**

Run: `python -m pytest tests/test_inject_anchors.py -v`
Expected: 全部通过

Run: `python -m pytest tests/ -q`
Expected: 77 passed（原 77 + 新增 1 - 0 = 78？——注意本任务加 1 个测试，见下方说明）

> 说明：Task 1 之前全量为 77（原 76 + 引用 margin 测试 1）。本任务 +1 = 78。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_inject_anchors.py
git commit -m "fix: 引用块空引用行不再注入锚点，消除段间空灰条"
```

---

### Task 2: 修复 B —— 删除段落末尾悬空 `<br />`

**Files:**
- Modify: `md_viewer.py`（新增 `_strip_trailing_br` 静态方法 + `reload_file` 调用）
- Test: `tests/test_quote_rendering.py`（新增一个测试方法）

**Interfaces:**
- Consumes: 无
- Produces: `_strip_trailing_br(html: str) -> str`（模块内静态方法，`reload_file` 调用）

- [ ] **Step 1: 写失败的测试**

在 `tests/test_quote_rendering.py` 的 TestCase 类新增：

```python
    def test_strip_trailing_br(self):
        self.assertEqual(
            MarkdownViewer._strip_trailing_br("<p>文字<br /></p>"),
            "<p>文字</p>",
        )
        # 段内换行的 br 不受影响
        self.assertEqual(
            MarkdownViewer._strip_trailing_br("<p>行1<br />\n行2</p>"),
            "<p>行1<br />\n行2</p>",
        )
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_quote_rendering.py::*test_strip_trailing_br -v`
Expected: FAIL（`AttributeError: MarkdownViewer has no attribute '_strip_trailing_br'`）

- [ ] **Step 3: 改代码**

(1) 在 `md_viewer.py` 的 `_style_blockquotes` 方法之后新增静态方法：

```python
    @staticmethod
    def _strip_trailing_br(html: str) -> str:
        """删除段落末尾的悬空 <br />。

        引用块末尾的空引用行经 nl2br 会转成段落末尾的 <br />，Qt 渲染为
        末尾空行盒（带背景的空灰条）。正常段落末尾本无 <br />，删除无副作用。
        """
        return re.sub(r'<br />\s*</p>', '</p>', html)
```

(2) 在 `reload_file()` 中 `html_body = self._style_blockquotes(html_body)`（约 942 行）之后新增一行：

```python
        html_body = self._strip_trailing_br(html_body)
```

改之前先 `Read` 确认原文。

- [ ] **Step 4: 运行测试确认通过 + 回归**

Run: `python -m pytest tests/test_quote_rendering.py -v`
Expected: 全部通过

Run: `python -m pytest tests/ -q`
Expected: 78 passed（Task 1 后 78，本任务 +1 = 79）

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_quote_rendering.py
git commit -m "fix: 删除段落末尾悬空 br，消除引用块末尾空灰条"
```

---

## Self-Review 结论

- **Spec 覆盖**：修复 A（段间空灰条）→ Task 1；修复 B（末尾空灰条）→ Task 2。设计文档 §9.2 两处修复均有对应任务。
- **占位符**：无 TBD/TODO，改代码与测试均给出完整内容。
- **类型一致性**：`_strip_trailing_br` 在 Task 2 定义并在 `reload_file` 调用，名称一致；测试断言 `lines[1] == ">"` 与修复逻辑（空引用行原样输出）一致。
- **测试数量核对**：Task 1 前 77，Task 1 后 78，Task 2 后 79（两任务各 +1）。
