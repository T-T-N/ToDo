# This file is required by Render and Heroku to properly serve the app
# It sets up gunicorn as the production web server

workers = 4  # Adjust based on available memory and CPU cores
threads = 2
worker_class = 'gthread'
bind = "0.0.0.0:$PORT"  # Use the PORT environment variable provided by the platform
timeout = 120  # Increase timeout for slower operations

# Handle SSL termination properly
forwarded_allow_ips = '*'
secure_scheme_headers = {
    'X-FORWARDED-PROTOCOL': 'ssl',
    'X-FORWARDED-PROTO': 'https',
    'X-FORWARDED-SSL': 'on'
}
