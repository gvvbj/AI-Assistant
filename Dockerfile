FROM python:3.12-slim

WORKDIR /workspace

# 1. 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV MPLBACKEND=Agg

# === 新增：替换系统源为清华源 (解决 apt-get 慢或失败的问题) ===
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 2. 安装系统依赖
RUN apt-get update && apt-get install -y \
    fonts-wqy-microhei \
    procps \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 3. 安装 Python 库 (你已经写了清华源，这步没问题)
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
    pandas \
    numpy \
    matplotlib \
    seaborn \
    openpyxl \
    tabulate \
    scikit-learn \
    yfinance \
    scipy \
    requests

# 4. 配置 Matplotlib 中文字体
RUN mkdir -p /root/.config/matplotlib && \
    echo "font.family: WenQuanYi Micro Hei" > /root/.config/matplotlib/matplotlibrc && \
    echo "axes.unicode_minus: False" >> /root/.config/matplotlib/matplotlibrc && \
    echo "Matplotlib config created."

CMD ["tail", "-f", "/dev/null"]