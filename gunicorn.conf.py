# Gunicorn configuration for Render deployment
import os
import multiprocessing

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
threads = 2
worker_class = 'sync'

# Binding
bind = "0.0.0.0:" + os.environ.get("PORT", "8000")
timeout = 120  # Increase timeout for slower operations

# Handle SSL termination properly
forwarded_allow_ips = '*'
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}
