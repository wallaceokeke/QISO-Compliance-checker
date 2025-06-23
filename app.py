from flask import Flask
from routes import setup_routes
import os

app = Flask(__name__)

# Use environment variable for security, fallback to default if not set
app.secret_key = os.environ.get("SECRET_KEY", "Qiso123456@2025")

# Register all routes
setup_routes(app)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Railway assigns this dynamically
    print("\n=== QISO Sentinel Booting ===")
    print(f"Running on port {port} | Powered by LeadDevCorps — Wallace Brown 🌍")
    app.run(host='0.0.0.0', port=port, debug=True)
