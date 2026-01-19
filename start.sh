#!/bin/bash
# Use PORT environment variable or default to 5000
PORT=${PORT:-5000}
gunicorn app:app --bind 0.0.0.0:$PORT