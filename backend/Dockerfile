# SmartNotes Backend Dockerfile
# 构建阶段
FROM python:3.11-slim AS builder

WORKDIR /app

# 复制依赖文件并安装（所有包都有预编译wheel，无需gcc）
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 运行阶段
FROM python:3.11-slim

WORKDIR /app

# 从构建阶段复制已安装的包
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制整个 backend 目录，保持 backend/ 子目录结构
COPY backend/ ./backend/

# 设置 Python 路径，让 Python 能找到 /app/backend 包
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# 设置 UTF-8 编码，解决中文乱码问题
ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
# 禁用 SSL 验证以解决 ChromaDB 嵌入模型下载时的 SSL 错误
ENV REQUESTS_CA_BUNDLE=""
ENV CURL_CA_BUNDLE=""
ENV PYTHONHTTPSVERIFY=0
ENV SSL_NO_VERIFY=1

EXPOSE 8000 8001 8002 8003 8010 8011

CMD ["uvicorn", "backend.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
