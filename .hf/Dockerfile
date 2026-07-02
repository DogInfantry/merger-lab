FROM python:3.12-slim

# WeasyPrint runtime deps (PDF memo generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces run as uid 1000; give it a writable home + app dir (yfinance cache)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
CMD ["streamlit", "run", "app/streamlit_app.py", \
     "--server.port", "7860", "--server.address", "0.0.0.0", \
     "--server.headless", "true"]
