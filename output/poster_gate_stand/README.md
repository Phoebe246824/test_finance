# Sentinel Edge 门型展架

本目录包含根据项目资料整理的研究生电子设计竞赛门型展架：

- `poster.html`：可编辑展架源文件，尺寸为 910 × 2048 px，对齐用户提供的模板比例。
- `poster.png`：使用 Chrome headless 从 HTML 导出的预览图。

内容依据：

- `docs/paper/paper_outline.md`
- `docs/paper/chapters/03_architecture.md`
- `docs/paper/chapters/04_multi_agent_design.md`
- `docs/paper/chapters/05_methods.md`
- `docs/paper/chapters/08_experiments.md`
- `scripts/finance_demo_cases.py`
- `README.md`

注意：AMD 锐龙 AI MAX+ 平台性能与能效实验在论文中仍是待补表格，因此展架没有编造端到端延迟、功耗或量化实测数值；相关位置已在展架底部说明，可在实测后替换。

重新导出 PNG：

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --screenshot=poster.png \
  --window-size=910,2048 poster.html
```
