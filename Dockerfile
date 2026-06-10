# ---------- 构建阶段 ----------
FROM python:3.11-slim AS builder

# 安装 Pillow 依赖（图像库编译需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    libwebp-dev \
    libopenjp2-7-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --upgrade pip && \
    python -m pip install --prefix=/install -r requirements.txt

# ---------- 运行阶段 ----------
FROM python:3.11-slim

# 安装 Pillow 运行时依赖（轻量）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    libfreetype6 \
    libwebp7 \
    libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制安装好的依赖和代码
COPY --from=builder /install /usr/local
COPY . /app

# 创建上传、输出和ZIP目录
RUN mkdir -p static/uploads static/output static/output/zips && chmod -R 777 static

# 非root用户运行更安全
RUN useradd -m appuser
USER appuser

# 环境变量配置
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1
ENV PORT=5010

EXPOSE 5010

# 从环境变量读取 SECRET_KEY
CMD ["gunicorn", "--bind", "0.0.0.0:5010", "--workers", "2", "app:app"]
