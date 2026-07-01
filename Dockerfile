FROM python:3.11-slim

WORKDIR /app

# Playwright 系统依赖
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    curl wget ca-certificates gnupg \
    libgtk-3-0 libgbm1 libasound2 libxshmfence1 \
    libnss3 libnspr4 libatk-bridge2.0-0 libatk1.0-0 libcups2 \
    libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libxau6 libxdmcp6 \
    libxcb1 libpango-1.0-0 libcairo2 \
    fonts-liberation fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install chromium && \
    playwright install-deps chromium

COPY . .

RUN mkdir -p data storage/image-packs logs

ENV PYTHONUNBUFFERED=1
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501 8000

CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port 8000 & streamlit run app.py"]
