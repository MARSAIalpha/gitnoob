import sys
import os

# Add the root directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from github_hub.server import app
    print("Server imported successfully")
except Exception as e:
    print(f"Error importing server: {e}")
    import traceback
    traceback.print_exc()
    
    # Create a minimal Flask app that returns the error
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/')
    def error_page():
        return f"<h1>Import Error</h1><pre>{str(e)}</pre>", 500
    
    @app.route('/api/<path:path>')
    def api_error(path):
        return jsonify({"error": str(e)}), 500
