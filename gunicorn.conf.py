# Gunicorn configuration for Render deployment
import os
import multiprocessing

# Worker processes
workers = 4  # Fixed number of workers for stability
threads = 1
worker_class = 'sync'
max_requests = 1000
max_requests_jitter = 50

# Binding
bind = "0.0.0.0:" + os.environ.get("PORT", "8000")
timeout = 30  # More reasonable timeout
keepalive = 5

# Handle SSL termination properly
forwarded_allow_ips = '*'
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}
