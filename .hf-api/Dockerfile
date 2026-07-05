# API Space (Option B backend) — separate from the Streamlit Space (.hf/).
# Returns rendered memo HTML, not PDF, so no WeasyPrint/pango deps needed.
# Build context is the repo root: it needs src/, api/ and data/.
FROM python:3.12-slim

# HF Spaces run as uid 1000; give it a writable home + app dir (yfinance cache)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user api/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

COPY --chown=user . .
RUN mkdir -p /home/user/app/data/cache

EXPOSE 7860
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "7860"]
