# 缩进代码围栏渲染修复 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Markdown 渲染前新增一步预处理，把缩进的代码围栏左移到顶格，使 `fenced_code` 扩展能正确识别为代码块。

**Architecture:** 在 `MarkdownViewer` 类中新增静态方法 `_dedent_fenced_blocks`（逐行扫描缩进围栏，保留相对缩进，左移到顶格），并在 `reload_file()` 中将其插入到 `_normalize_list_indent` 之前执行。仅修改一个文件，不改用户源文件。

**Tech Stack:** Python 3, PySide6, `re`, `markdown`（fenced_code 扩展）

## Global Constraints

- 仅修改 `md_viewer.py`，不引入新依赖，不碰其他文件
- 纯内存预处理，不改磁盘上的 `.md` 文件
- 顶格围栏行为完全不变（零回归）
- 中文注释，正则预编译，与 `_normalize_list_indent` 风格一致

---

### Task 1: 新增 `_dedent_fenced_blocks` 静态方法

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py` — 在 `_normalize_list_indent` 之前插入新方法（约第 706 行之前）

**Interfaces:**
- Produces: `MarkdownViewer._dedent_fenced_blocks(content: str) -> str` — 静态方法，输入原始 Markdown 文本，返回去缩进后的文本

- [ ] **Step 1: 在 `_normalize_list_indent` 之前插入新方法**

在 `md_viewer.py` 第 706 行（`@staticmethod def _normalize_list_indent` 之前）插入：

```python
    @staticmethod
    def _dedent_fenced_blocks(content: str) -> str:
        """把缩进的代码围栏（```` ``` ````` / `~~~`）及其内部行整体左移到顶格。

        python-markdown 的 fenced_code 扩展不识别缩进在列表项内的围栏，
        会把 ``` 退化成内联 code，导致多行内容在 Qt 富文本里挤成一行。
        本函数在渲染前��所有缩进围栏拍平到顶格，使 fenced_code 能正确识别。
        围栏内代码的相对缩进予以保留。
        """
        lines = content.split('\n')
        out = []
        i = 0
        open_re = re.compile(r'^(\s*)(`{3,}|~{3,})(.*)$')
        close_re = re.compile(r'^(\s*)(`{3,}|~{3,})\s*$')
        while i < len(lines):
            line = lines[i]
            m = open_re.match(line)
            if m and m.group(1):  # 缩进围栏开始
                indent = m.group(1)
                fence_char = m.group(2)[0]    # ` 或 ~
                fence_len = len(m.group(2))   # 反引号/波浪号个数
                out.append(line[len(indent):])
                i += 1
                while i < len(lines):
                    inner = lines[i]
                    cm = close_re.match(inner)
                    # 闭合判断：同类型且数量 >= 开���围栏
                    if cm and cm.group(2)[0] == fence_char and len(cm.group(2)) >= fence_len:
                        out.append(inner[len(indent):] if inner.startswith(indent) else inner.lstrip())
                        i += 1
                        break
                    out.append(inner[len(indent):] if inner.startswith(indent) else inner.lstrip())
                    i += 1
            else:
                out.append(line)
                i += 1
        return '\n'.join(out)
```

- [ ] **Step 2: 运行独立测试脚本验证函数正确性**

```bash
cd g:/UGit/popup && python -c "
import sys; sys.argv=['x']
from PySide6.QtWidgets import QApplication; app=QApplication(sys.argv)
from md_viewer import MarkdownViewer as M
import markdown

raw = open('G:/UGit/summarize-knowledge/SKILL.md', encoding='utf-8').read()
fixed = M._dedent_fenced_blocks(raw)
fixed = M._normalize_list_indent(fixed)
md = markdown.Markdown(extensions=['tables','fenced_code','codehilite','toc','nl2br'])
html = md.convert(fixed)
codehilite_cnt = html.count('class=\"codehilite\"')
assert codehilite_cnt == 6, f'Expected 6 codehilite blocks, got {codehilite_cnt}'
assert html.count('<code>bash') == 0, 'Should have 0 inline <code>bash'
print(f'PASS: {codehilite_cnt} codehilite blocks, 0 inline <code>bash')
"
```

- [ ] **Step 3: 验证顶格围栏不受影响（回归）**

```bash
cd g:/UGit/popup && python -c "
import sys; sys.argv=['x']
from PySide6.QtWidgets import QApplication; app=QApplication(sys.argv)
from md_viewer import MarkdownViewer as M
import markdown

# 顶格围栏文档
src = '''## Test
\`\`\`python
print('hello')
\`\`\`
'''
md = markdown.Markdown(extensions=['tables','fenced_code','codehilite','toc','nl2br'])
# 原始渲染
orig = md.convert(M._normalize_list_indent(src))
# 先 dedent 再 normalize 的渲染
new = md.convert(M._normalize_list_indent(M._dedent_fenced_blocks(src)))
assert orig == new, 'Top-level fence should be unchanged'
print('PASS: top-level fence unchanged')
"
```

- [ ] **Step 4: 验证相对缩进保留**

```bash
cd g:/UGit/popup && python -c "
import sys; sys.argv=['x']
from PySide6.QtWidgets import QApplication; app=QApplication(sys.argv)
from md_viewer import MarkdownViewer as M

src = '''- x:
  \`\`\`python
  def foo():
      if True:
          return 1
  \`\`\`
'''
result = M._dedent_fenced_blocks(src)
lines = result.split('\n')
# def 应顶格
assert 'def foo():' in lines, f'def not found in {lines}'
# if True: 应保留 4 空格
idx = lines.index('def foo():')
assert lines[idx+1] == '    if True:', f'Expected 4-space indent, got {lines[idx+1]!r}'
# return 1 应保留 8 空格
assert lines[idx+2] == '        return 1', f'Expected 8-space indent, got {lines[idx+2]!r}'
print('PASS: relative indent preserved')
"
```

- [ ] **Step 5: 验证 Tab 缩进**

```bash
cd g:/UGit/popup && python -c "
import sys; sys.argv=['x']
from PySide6.QtWidgets import QApplication; app=QApplication(sys.argv)
from md_viewer import MarkdownViewer as M
import markdown

src = '- x:\n\t\`\`\`bash\n\tgit init\n\t\`\`\`\n'
fixed = M._dedent_fenced_blocks(src)
fixed = M._normalize_list_indent(fixed)
md = markdown.Markdown(extensions=['tables','fenced_code','codehilite','toc','nl2br'])
html = md.convert(fixed)
assert html.count('class=\"codehilite\"') == 1, f'Expected 1 codehilite, got {html.count(\"class=codehilite\")}'
print('PASS: tab indent works')
"
```

- [ ] **Step 6: 验证四反引号嵌套**

```bash
cd g:/UGit/popup && python -c "
import sys; sys.argv=['x']
from PySide6.QtWidgets import QApplication; app=QApplication(sys.argv)
from md_viewer import MarkdownViewer as M
import markdown

src = '''- x:
  \`\`\`\`markdown
  \`\`\`python
  print(1)
  \`\`\`
  \`\`\`\`
'''
fixed = M._dedent_fenced_blocks(src)
fixed = M._normalize_list_indent(fixed)
md = markdown.Markdown(extensions=['tables','fenced_code','codehilite','toc','nl2br'])
html = md.convert(fixed)
assert html.count('class=\"codehilite\"') == 1, f'Expected 1 codehilite, got {html.count(\"class=codehilite\")}'
print('PASS: nested 4-backtick fence works')
"
```

- [ ] **Step 7: Commit**

```bash
cd g:/UGit/popup && git add md_viewer.py && git commit -m "feat: 新增 _dedent_fenced_blocks 预处理方法

缩进的代码围栏（如列表项内的 ```bash）会被 fenced_code 扩展误判为
内联 code 导致多行内容挤成一行。此方法在渲染前把缩进围栏左移到顶格，
保留围栏内相对缩进，使 fenced_code 能正确识别为代码块。"
```

---

### Task 2: 接入 `reload_file` 渲染管线

**Files:**
- Modify: `g:\UGit\popup\md_viewer.py:670-674` — 修改 `reload_file()` 中预处理调用顺序

**Interfaces:**
- Consumes: `MarkdownViewer._dedent_fenced_blocks(content: str) -> str`（Task 1 产出）
- Produces: 无新接口，修改 `reload_file()` 内部行为

- [ ] **Step 1: 修改 `reload_file` 调用顺序**

将 `md_viewer.py` 第 670-674 行：

```python
        normalized = self._normalize_list_indent(content)
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        html_body = md.convert(normalized)
```

改为：

```python
        # 先拍平缩进围栏，再规范列表缩进（必须先 dedent 后 normalize，
        # 否则 normalize ��动的缩进量会导致围栏对不齐）
        normalized = self._dedent_fenced_blocks(content)
        normalized = self._normalize_list_indent(normalized)
        md = markdown.Markdown(
            extensions=["tables", "fenced_code", "codehilite", "toc", "nl2br"]
        )
        html_body = md.convert(normalized)
```

- [ ] **Step 2: 验证修改正确（语法检查 + 原有测试）**

```bash
cd g:/UGit/popup && python -c "import ast; ast.parse(open('md_viewer.py', encoding='utf-8').read()); print('PASS: syntax OK')"
```

- [ ] **Step 3: 整篇端到端验证（SKILL.md 完整渲染）**

```bash
cd g:/UGit/popup && python -c "
import sys; sys.argv=['x']
from PySide6.QtWidgets import QApplication; app=QApplication(sys.argv)
from md_viewer import MarkdownViewer as M
import markdown

raw = open('G:/UGit/summarize-knowledge/SKILL.md', encoding='utf-8').read()
# 模拟 reload_file 的实际管线
normalized = M._dedent_fenced_blocks(raw)
normalized = M._normalize_list_indent(normalized)
md = markdown.Markdown(extensions=['tables','fenced_code','codehilite','toc','nl2br'])
html = md.convert(normalized)
assert html.count('class=\"codehilite\"') == 6
assert '<code>bash' not in html
assert '<li>' in html  # 列表仍然存在（normalize 生效）
print('PASS: end-to-end render of SKILL.md')
"
```

- [ ] **Step 4: Commit**

```bash
cd g:/UGit/popup && git add md_viewer.py && git commit -m "fix: 在 reload_file 中先执行 _dedent_fenced_blocks

必须先在 render 前拍平缩进围栏、再执行 _normalize_list_indent，
否则 normalize 改动缩进量会导致围栏无法正确去缩进。"
```

---

### Task 3: 手动验证测试清单

**Files:**
- 无代码修改

- [ ] **1. 打开 SKILL.md**：确认第 46-52 行 bash 代码块多行显示，语法高亮生效
- [ ] **2. 全部 6 个围栏**：确认均为代码块，无内联 code 挤成一行
- [ ] **3. 顶格围栏回归**：打开普通顶格代码块文档，渲染无变化
- [ ] **4. 相对缩进保留**：Python 函数体（`def`→`if`→`return`）缩进层级正确
- [ ] **5. 波浪号围栏**：`~~~` 缩进围栏同样修复
- [ ] **6. 未闭合围栏**：文档不崩溃、不吞内容
- [ ] **7. normalize 回归**：列表 3 空格→4 空格功能正常（新顺序下）
- [ ] **8. F5 刷新**：文件监听自动刷新后修复依旧生效
- [ ] **9. 四反引号嵌套**：` ```` ` 包 ` ``` ` 正常
- [ ] **10. 文档级缩进围栏**：不在列表内但围栏前有空白，正确去缩进
- [ ] **11. 无空行紧贴列表**：列表文字下一行直接是缩进围栏，正常渲染
- [ ] **12. Tab 缩进围栏**：Tab 缩进同样识别并去缩进
