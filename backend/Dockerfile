
FROM python:3.11-slim

WORKDIR /app

# 安装 SUMO 主程序所需的 Linux 运行时依赖
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        libx11-6 \
        libxext6 \
        libxrender1 \
        libgl1 \
        libatomic1 \
        libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖及 SUMO 1.28.0
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 配置 SUMO 环境变量
ENV SUMO_HOME=/usr/local/lib/python3.11/site-packages/sumo
ENV PATH="${SUMO_HOME}/bin:${PATH}"

COPY app ./app
COPY tests ./tests

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
