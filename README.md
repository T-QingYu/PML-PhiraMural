# PML - PhiraMural v1.0

将 Phira 谱面（RPE 格式）的静态背景替换为视频背景的工具。

## 功能

- 支持文件夹和压缩包（.pez/.zip）两种输入方式
- 自动验证 RPE 格式
- 自动剥离视频音轨（需要 FFmpeg，可选）
- 自动清洗 RPE v170 不兼容字段
- 生成 Phira 所需的 info.yml 和 extra.json
- 支持统一重命名文件
- 支持压缩输出为 .zip 或 .pez 格式

## 使用方法

1. 下载解压后，双击 `PML_PhiraMural.exe` 启动
2. 选择谱子文件夹或压缩包
3. 选择视频背景文件
4. 点击「生成」

## 下载

在 [Releases](../../releases) 页面下载最新版本，解压后即可使用。

无需安装 Python，双击 exe 直接运行。

## 系统要求

- Windows 10/11

## FFmpeg（可选）

FFmpeg 用于自动剥离视频音轨。如果不安装，程序会直接复制原视频（带声音）。

下载地址：https://ffmpeg.org/download.html

## 技术栈

- Python 3.12 + tkinter
- PyInstaller（打包）

## 开发者

© 2026 青雨
