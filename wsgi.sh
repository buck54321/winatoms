uwsgi --http localhost:5001 --http-websockets --socket :5000 --asyncio 100 --greenlet  --master  --wsgi winatoms:app --python-autoreload 1
