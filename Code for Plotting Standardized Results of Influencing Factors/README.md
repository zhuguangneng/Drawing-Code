# 标准因素两级树状图生成代码

该代码包用于从已经整理好的 `visualization_data.json` 重新生成论文版中英文两级树状图。

它不是AI图片生成程序。图形由结构化数据、固定排序和确定性的节点坐标计算产生，同一输入和字体配置可以重复生成相同内容与布局。

## 文件说明

- `generate_factor_tree_images.py`：建议直接运行的精简入口脚本。
- `production_renderer.py`：本项目正式运行时使用的绘图核心，保留原始实现以便审计；请不要直接运行该文件。
- `visualization_data.json`：本次正式图表使用的数据快照。
- `requirements.txt`：Python依赖。

## 输出内容

默认同时生成中文和英文版本，每种语言包含：

- SVG：可编辑矢量图；
- PDF：单页矢量图；
- PNG：按相同几何原生重绘的600 DPI位图；
- `render_manifest.json`：尺寸、节点数、文件哈希和验证结果。

默认图幅为7.0 × 10.025英寸。600 DPI PNG为4200 × 6015像素。

## 安装

建议使用Python 3.12，在本目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 直接运行

```powershell
python generate_factor_tree_images.py
```

输出会写入本目录下的 `generated_figures` 文件夹。

指定输入和输出目录：

```powershell
python generate_factor_tree_images.py `
  --data visualization_data.json `
  --output-dir generated_figures
```

只生成英文版：

```powershell
python generate_factor_tree_images.py --language en
```

改变PNG分辨率：

```powershell
python generate_factor_tree_images.py --dpi 600
```

## 字体

正式图使用以下Windows字体：

- 中文常规：微软雅黑，找不到时使用黑体；
- 中文粗体：微软雅黑粗体，找不到时使用黑体；
- 英文常规：Arial；
- 英文粗体：Arial Bold。

若在非Windows环境运行，或需要期刊指定字体，可以显式传入字体文件：

```powershell
python generate_factor_tree_images.py `
  --cn-regular-font "D:\Fonts\NotoSansCJK-Regular.ttc" `
  --cn-bold-font "D:\Fonts\NotoSansCJK-Bold.ttc" `
  --en-regular-font "D:\Fonts\Arial.ttf" `
  --en-bold-font "D:\Fonts\Arial-Bold.ttf"
```

更换字体可能改变自动换行，从而产生轻微排版变化；正式复现时应使用相同字体。

即使只生成英文版，共享布局仍会同时测量中英文文本，因此四个字体文件都必须可用。SVG保留可编辑文字并引用字体族，不嵌入字体；在另一台电脑编辑SVG时，应安装相同字体或先将文字转为轮廓。字体文件能否随代码再分发取决于其许可证，本代码包未附带字体文件。

## 输入JSON的关键字段

脚本至少需要：

- `metrics`：类别数、图示因素数、图示频数和节点数；
- `category_summary`：一级分类中英文名、总频次、图示频次、颜色和顺序；
- `main_rows`：频数≥2的标准因素中英文名、频数、一级分类和类内顺序；
- `titles`：中英文标题、副标题和图下注释，可选。

脚本启动后会检查：

- 一级分类数量；
- 频数≥2因素数量；
- 图示频数总和；
- 节点数量；
- 重复因素键；
- 中英文名称是否完整。

输出后还会检查SVG节点数、PDF页数与尺寸、PNG像素尺寸和DPI元数据。任何检查失败都会以非零状态退出。

`render_manifest.json`还会记录Python与依赖版本、实际使用的四个字体路径及SHA-256、代码哈希和输出文件哈希。SVG与PNG在相同数据、代码、字体和库版本下可以稳定复现；PDF通常含运行时间或内部ID，因此应以页面尺寸、节点内容和视觉一致性验证，不应要求每次PDF字节哈希完全相同。

## 论文使用提示

- 排版时优先使用PDF或SVG；WPS/Word兼容性不足时再使用600 DPI PNG。
- 该图应按通栏或整页宽度使用，不要缩成单栏。
- 图中仅显示频数≥2的标准因素；频数为1的因素应在附表中报告。
- `n`表示标准因素在有效数据行中的出现频数，不是效应量。
