# 7. Naive-Bayes · 工作要求与分析脚本

本目录存放本节课的**工作计划、实验 notebook、分析脚本、数据集说明与依赖声明**。

## 存放内容

- `WORKPLAN.md` / `plan.md` / `experiment-design.md` 等：课程工作要求与实验设计
- `notebooks/` `notebook/`：实验 notebook（`.ipynb`）
- `scripts/` `experiment/`：分析与构建脚本（`.py` / `.mjs`）
- `requirements.txt`：原始依赖声明（若为空，以本 readme 为准）

## 运行环境与软件需求

- Python 3.10+（推荐 3.10 / 3.11）
- Jupyter / VS Code（用于打开 `.ipynb`）
- Node.js（仅当目录内存在 `.mjs` 脚本，用于生成 HTML/PDF 报告）

### 主要 Python 依赖

由脚本 import 静态扫描得出，建议使用如下命令安装：

```bash
pip install numpy pandas scipy scikit-learn matplotlib pillow python-docx nbformat nbclient ipython pywin32
```

> 注：依赖列表来自静态扫描，可能不完整；`pywin32` 仅在 Windows 下需要。若运行报错，请按报错信息补装对应包。
