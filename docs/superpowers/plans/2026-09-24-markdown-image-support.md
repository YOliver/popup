# Markdown 图片显示支持 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Popup 正确渲染 Markdown 中引用的本地相对路径图片（常见位图格式）。

**Architecture:** 在渲染前把 md 文件所在目录设为 `QTextDocument` 的 `baseUrl`，Qt 会以该目录为基准解析 `<img>` 的相对 `src`，通过内置资源加载机制读取本地文件并用 `QImageReader` 解码显示。基准 URL 构造逻辑抽取为可单元测试的纯静态方法 `_build_base_url()`。

**Tech Stack:** Python 3.8+、PySide6（QUrl / QTextDocument）、标准库 unittest。

## Global Constraints

- 不引入新依赖（测试使用标准库 `unittest`，不用 pytest）。
- 仅修改 `md_viewer.py`，不触碰其他模块（渲染预处理、目录、搜索、托盘等）。
- 代码注释、commit message 使用中文。
- 支持范围：本地相对路径图片 + 常见位图（PNG/JPG/GIF/BMP；GIF 仅首帧静态显示）。
- 非目标：SVG、网络图片、绝对路径、base64/data URI、图片变化自动刷新。

---

### Task 1: 新增 `_build_base_url` 纯函数（TDD）

**Files:**
- Modify: `md_viewer.py:48`（QtCore 导入行新增 `QUrl`）
- Modify: `md_viewer.py:783`（`_normalize_list_indent` 方法之后，新增 `_build_base_url` 静态方法）
- Test: `tests/test_base_url.py`（新建）

**Interfaces:**
- Consumes: 无（首个任务）。
- Produces: `MarkdownViewer._build_base_url(file_path: str) -> QUrl`，供 Task 2 在 `reload_file()` 中调用。输入为 md 文件的绝对路径，返回指向其所在目录、以 `/` 结尾的 `file:///` URL。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_base_url.py`：

```python
import os
import unittest

from md_viewer import MarkdownViewer


class TestBuildBaseUrl(unittest.TestCase):
    def test_normal_subdir(self):
        path = os.path.join("C:\\", "foo", "bar", "readme.md")
        url = MarkdownViewer._build_base_url(path)
        self.assertEqual(url.toLocalFile(), "C:/foo/bar/")

    def test_root_dir(self):
        url = MarkdownViewer._build_base_url("C:\\readme.md")
        self.assertEqual(url.toLocalFile(), "C:/")

    def test_path_with_spaces(self):
        path = os.path.join("C:\\", "my dir", "readme.md")
        url = MarkdownViewer._build_base_url(path)
        self.assertEqual(url.toLocalFile(), "C:/my dir/")

    def test_path_with_chinese(self):
        path = os.path.join("C:\\", "中文目录", "readme.md")
        url = MarkdownViewer._build_base_url(path)
        self.assertEqual(url.toLocalFile(), "C:/中文目录/")

    def test_base_url_is_directory(self):
        url = MarkdownViewer._build_base_url("C:\\foo\\readme.md")
        self.assertTrue(url.path().endswith("/"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试验证失败**

在项目根目录 `g:\UGit\popup` 运行：

```bash
python -m unittest discover -s tests -v
```

Expected: FAIL，报错 `AttributeError: type object 'MarkdownViewer' has no attribute '_build_base_url'`（`from md_viewer import MarkdownViewer` 本身成功，仅方法缺失）。

- [ ] **Step 3: 实现最小代码**

**改动 1**：`md_viewer.py:48` 的 QtCore 导入行新增 `QUrl`：

```python
from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QEvent, QUrl
```

**改动 2**：在 `md_viewer.py` 中 `_normalize_list_indent` 方法之后（约第 783 行 `return '\n'.join(out)` 之后、`on_file_changed` 之前）新增静态方法：

```python
    @staticmethod
    def _build_base_url(file_path: str) -> QUrl:
        """返回 md 文件所在目录的基准 URL，供 QTextBrowser 解析相对路径图片。

        目录末尾必须带分隔符，否则 QUrl.fromLocalFile 会把路径当文件处理，
        导致相对路径错误解析到父目录；根目录（如 C:\\）的 dirname 已带尾随
        分隔符，故用 endswith 判断避免重复追加（重复追加会产出损坏的 C://）。
        """
        base_dir = os.path.dirname(file_path)
        if not base_dir.endswith(os.sep):
            base_dir += os.sep
        return QUrl.fromLocalFile(base_dir)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m unittest discover -s tests -v
```

Expected: PASS，5 个测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add md_viewer.py tests/test_base_url.py
git commit -m "feat: 新增 _build_base_url 用于解析相对路径图片基准目录"
```

---

### Task 2: 在 reload_file 中接入 baseUrl 设置

**Files:**
- Modify: `md_viewer.py:687`（`reload_file()` 中 `setHtml()` 调用处）

**Interfaces:**
- Consumes: `MarkdownViewer._build_base_url(file_path: str) -> QUrl`（Task 1 产出）。
- Produces: 渲染时 `QTextDocument.baseUrl` 指向 md 文件所在目录，使 `<img src="相对路径">` 能被解析显示。

- [ ] **Step 1: 修改 reload_file**

`md_viewer.py` 的 `reload_file()` 中，把这一行（当前约第 687 行）：

```python
        self.text_browser.setHtml(self.wrap_html(html_body))
```

替换为：

```python
        base_url = self._build_base_url(self.file_path)
        self.text_browser.document().setBaseUrl(base_url)
        self.text_browser.setHtml(self.wrap_html(html_body))
```

说明：先 `setBaseUrl()` 再 `setHtml()`（已实测 `setHtml()` 不会重置已设置的 baseUrl）。

- [ ] **Step 2: 手动冒烟测试**

准备测试目录 `g:\UGit\popup\_smoke\`，放入以下文件：

`_smoke\readme.md`：

```markdown
# 图片测试

## 子目录图片
![子目录](./img/pic.png)

## 中文图片
![中文](图片.png)

## 空格图片
![空格](my image.png)

## 缺失图片
![缺失](not_exists.png)
```

`_smoke\img\pic.png`、`_smoke\图片.png`、`_smoke\my image.png`：任意 PNG 图片（三份内容可相同）。

运行并逐项验证：

```bash
python md_viewer.py _smoke/readme.md
```

Expected 验证清单：
1. 子目录图片 `./img/pic.png` 正常显示。
2. 中文文件名 `图片.png` 正常显示。
3. 空格文件名 `my image.png` 正常显示。
4. 缺失图片 `not_exists.png` 显示 alt 文本「缺失」，程序不崩溃。
5. 回归：F5 刷新、目录边栏跳转、Ctrl+F 搜索、Ctrl+B 目录折叠均正常。

- [ ] **Step 3: 清理冒烟测试临时目录**

```bash
rm -rf _smoke
```

确认 `_smoke` 不在 git 中（`git status` 无该目录）。

- [ ] **Step 4: 提交**

```bash
git add md_viewer.py
git commit -m "feat: reload_file 设置 baseUrl 支持本地相对路径图片显示"
```

---

## 自审记录

- **Spec 覆盖**：spec 第 2 节目标（本地相对路径图片 + 位图）→ Task 2 接入；第 4 节改动点（导入 QUrl、设置 baseUrl）→ Task 1 + Task 2；第 5 节边界（子目录/中文/空格/根目录）→ Task 1 单元测试覆盖；第 6 节手动冒烟 → Task 2 Step 2。
- **占位符扫描**：无 TBD/TODO，所有步骤含完整代码或命令。
- **类型一致性**：`_build_base_url(file_path: str) -> QUrl` 在 Task 1 定义、Task 2 调用，签名一致。
