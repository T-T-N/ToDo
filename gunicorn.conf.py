# Gunicorn configuration for Render deployment
import os

# Worker processes
workers = int(os.getenv('WEB_CONCURRENCY', 4))  # Default to 4 workers
threads = int(os.getenv('PYTHON_MAX_THREADS', 2))
worker_class = 'gthread'

# Binding
port = os.getenv('PORT', '8000')
bind = f"0.0.0.0:{port}"
timeout = 120  # Increase timeout for slower operations

# Handle SSL termination properly
forwarded_allow_ips = '*'
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}
