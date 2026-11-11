import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError

app = Flask(__name__)

MONGODB_URI = os.environ.get(
    "MONGODB_URI",
    "mongodb://localhost:27017/flask_db",
)
client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
)
db = client.get_default_database()
if db is None:
    db = client["flask_db"]
collection = db["data"]


@app.get("/")
def index():
    return (
        "Welcome to the Flask app! The current time is: "
        f"{datetime.now(timezone.utc).isoformat()}",
        200,
        {"Content-Type": "text/plain; charset=utf-8"},
    )


@app.get("/healthz")
def healthz():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ok", "database": "reachable"}), 200
    except PyMongoError:
        return jsonify({"status": "error", "database": "unreachable"}), 503


@app.route("/data", methods=["GET", "POST"])
def data():
    try:
        if request.method == "POST":
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict) or not payload:
                return jsonify({"error": "Request body must be a non-empty JSON object"}), 400
            collection.insert_one(payload)
            return jsonify({"status": "Data inserted"}), 201

        documents = list(collection.find({}, {"_id": 0}))
        return jsonify(documents), 200
    except PyMongoError:
        app.logger.exception("MongoDB operation failed")
        return jsonify({"error": "Database operation failed"}), 503


@app.get("/readyz")
def readyz():
    try:
        client.admin.command("ping")
        return jsonify({"status": "ready"}), 200
    except PyMongoError:
        return jsonify({"status": "not-ready"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
