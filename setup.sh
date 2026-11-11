#!/usr/bin/env bash
# Instala todo lo necesario para el editor de VSL (idempotente).
set -e
cd "$(dirname "$0")"
if ! command -v ffmpeg >/dev/null || ! command -v espeak-ng >/dev/null; then
  (apt-get install -y -q ffmpeg espeak-ng fonts-inter tesseract-ocr >/dev/null 2>&1 \
   || (apt-get update -q >/dev/null && apt-get install -y -q ffmpeg espeak-ng fonts-inter tesseract-ocr >/dev/null)) || true
fi
pip install -q -r requirements.txt
# Pre-descarga el modelo de transcripción para que la primera edición sea rápida
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8')" >/dev/null 2>&1 || true
python -m vsl_editor sfx-generar >/dev/null
echo "Editor de VSL listo ✔"
