# RiskDraft — runnable container for the Streamlit prototype.
#
#   docker build -t riskdraft .
#   docker run -p 8501:8501 riskdraft                 # mock mode, offline
#   docker run -p 8501:8501 -e LLM_PROVIDER=anthropic \
#       -e ANTHROPIC_API_KEY=sk-... riskdraft          # real LLM
#
# Then open http://localhost:8501
FROM python:3.11-slim

# tesseract is needed only if you use photo/OCR capture; cheap to include.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
