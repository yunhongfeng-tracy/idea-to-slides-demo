---
name: nano-banana-pro-image
description: 将想法变成白板手绘风格图片。用户通过模板输入想法，AI 自动分析内容、选择图类型、生成提示词并调用 Nano Banana Pro API 出图。触发词：想法变成图片、白板图、手绘图、可视化想法。

---

# 想法变成图片

## 概述

将用户的想法、笔记、分析等文字内容，自动转化为白板手绘风格的可视化图片。

## 前置条件

1. 安装 Python 依赖：`pip install requests`
2. 项目根目录放置 `api.md` 文件，内容为 API Key

## 完整工作流

### 第一步：用户输入

用户通过模板提供关键信息（也可自由输入，AI 自动提炼）：

```
【想法】：（核心想法，自由描述）
【角色】：（涉及哪些角色/对象，它们之间什么关系）
【重点】：（最想让看图的人记住什么）
【补充】：（容易遗漏的细节，没有就不填）
```

### 第二步：AI 自动处理

1. 分析内容，梳理结构化想法
2. 自动选择图类型（不需用户选）：
   - 有对比/转变 → **对比型**
   - 有多角色交互 → **架构型**
   - 有时间演进 → **时间线型**
   - 有线性流转 → **流程型**
   - 有概念展开 → **中心辐射型**
3. 基于风格底板 + 内容生成完整提示词
4. 保存文档到 `doc/XX-场景名.md`

### 第三步：生成图片

```bash
python -X utf8 py/generate_image.py --prompt "完整提示词" --output "py/XX-场景名-图类型.png" --aspect-ratio 16:9 --image-size 4K
```

### 第四步：用户反馈

用户看图后按需微调。目标 1-2 轮完成。

## 提示词风格底板

所有白板图提示词末尾追加此风格描述（不用每次重写）：

```
Style: clean white whiteboard background, hand-drawn sketch like Excalidraw, thick colorful marker strokes, casual handwritten Chinese labels, simple doodle icons, wobbly hand-drawn arrows. No photorealistic elements.
```

## 提示词编写规则

- 主体用英文，开头加 `ALL TEXT MUST BE IN CHINESE`
- 所有标签直接写中文（如 `labeled '自动协商'`）
- 仅专有名词/品牌名保留英文
- 关键中文词重复出现，防止 AI 写错字
- 用不同颜色区分角色/阶段

## 脚本参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--prompt` | - | 提示词文本 |
| `--prompt-file` | - | 提示词文件路径 |
| `--output` | `output.png` | 输出图片路径 |
| `--aspect-ratio` | `3:4` | 宽高比（白板图推荐 `16:9`） |
| `--image-size` | - | 输出尺寸（推荐 `4K`） |
| `--model` | `nano-banana-pro` | 模型名称 |
| `--api-file` | 自动向上搜索 | api 文件路径 |
| `--poll-interval` | `5` | 轮询间隔（秒） |
| `--max-wait` | `300` | 最长等待时间（秒） |
| `--timeout` | `30` | HTTP 超时（秒） |
| `--verify-ssl` | 关闭 | 启用 SSL 校验 |

## API 配置

api 文件支持两种格式：

```
# 格式1：纯 key
sk-xxxxxxxxxxxxxxxx

# 格式2：key=value
GRSAI_API_KEY=sk-xxxxxxxxxxxxxxxx
GRSAI_BASE_URL=https://api.grsai.com
```

优先级：命令行参数 > 环境变量 > api 文件

## 中文标注规范

- **中文优先**：所有标签、说明、步骤描述、对话气泡等一律使用中文
- **英文例外**：仅专有名词/品牌名（如 `OpenClaw`、`Agent`）、无通用中文译名的技术术语

## 备注

- 默认 API 地址：`https://api.grsai.com`
- 网络请求自动重试（5 次，指数退避，应对 SSL/连接错误）
- 不要在提示词或日志中输出 API Key
