# KeepGeneration-Batch: 网页版Keep跑步截图批量生成器

基于 [KeepGeneration-Web](https://github.com/eltsen00/KeepGeneration-Web) 开发的**批量版**，支持在指定范围内随机生成多张Keep风格跑步截图。

## 🚀 快速开始

```bash
pip install flask pillow
python app.py
```
浏览器打开 **http://localhost:5010** 即可使用

## ✨ 相比原项目新增功能

### 批量随机生成
- **指定生成数量**（最大100张）
- **所有运动数据在范围内独立随机**：每张的公里数、时间、配速、爬升、步频、运动负荷均不同
- **地图随机抽取**：从指定文件夹中随机选择，连续两张不重复
- **天气按权重随机**：晴/多云/阴天可分别设权重
- **温度范围随机**：每次在 min-max 间随机取值
- **结束时间范围随机**：每次在 min-max 间随机取值
- **日期自动递增**：批量时每张延后一天
- **电池电量图标随机**：每次在指定范围内随机选择电池图标叠加
- **状态栏时间偏移**：左上角时间比实际结束时间晚 0~15 分钟

### 地图管理
- 从**指定文件夹**读取地图，增减图片即时生效
- 勾选地图组成随机池，未勾选则使用全部

### 批量下载
- 画廊展示所有生成结果
- 一键打包下载 ZIP

## 🛠️ 本地运行

```bash
pip install flask pillow
python app.py
# 浏览器打开 http://localhost:5010
```

## 🐳 Docker 部署

```bash
docker build -t keep-batch .
docker run -d --name keep-batch -p 5010:5010 keep-batch
```

## 📂 目录结构

```
KeepGeneration-Batch/
├── app.py                 # Flask 后端
├── KeepSultan.py          # 核心生成逻辑
├── templates/index.html   # 前端页面
├── fonts/                 # 字体文件
├── static/
│   ├── battery/           # 电池图标 (2.png ~ 100.png)
│   ├── maps/              # 预设地图
│   ├── default_avatar.png
│   └── default_template.png
└── requirements.txt
```

## ❤️ 致谢

- 原项目 [KeepSultan](https://github.com/Carzit/KeepSultan) by [Carzit](https://github.com/Carzit)
- 网页版 [KeepGeneration-Web](https://github.com/eltsen00/KeepGeneration-Web) by [eltsen00](https://github.com/eltsen00)
- 本项目在此基础上增加批量生成、随机化等功能

## 📜 免责声明

本工具仅供个人学习与研究使用，与Keep官方无任何关联。
