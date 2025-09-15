from flask import Flask, request, jsonify, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from flask_cors import CORS  # <-- Added for CORS

from rembg import remove, new_session
from PIL import Image

import io, os, uuid
from datetime import timedelta

# Optional GCS
try:
    from google.cloud import storage
except Exception:
    storage = None

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)  # <-- Enable CORS globally
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Config
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER", "static/processed_images")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Rembg model session (preload once)
MODEL_NAME = os.getenv("REMBG_MODEL", "u2net")
session = new_session(MODEL_NAME)  # triggers model load; fast afterward

# GCS config (optional)
GCS_BUCKET = os.getenv("GCS_BUCKET")
GCS_PREFIX = os.getenv("GCS_PREFIX", "processed")
SIGNED_SECS = int(os.getenv("GCS_SIGNED_URL_SECONDS", "0"))
use_gcs = bool(GCS_BUCKET) and storage is not None
gcs_client = storage.Client() if use_gcs else None


def _remove_bg_and_flatten_to_white(file_storage) -> Image.Image:
    src = Image.open(file_storage.stream).convert("RGBA")
    cut = remove(src, session=session)  # use global session
    white = Image.new("RGBA", cut.size, (255, 255, 255, 255))
    white.paste(cut, mask=cut.split()[3])
    return white.convert("RGB")

def _save_local(img: Image.Image, out_name: str) -> str:
    out_path = os.path.join(OUTPUT_FOLDER, out_name)
    img.save(out_path, format="JPEG", quality=95, optimize=True)
    return url_for("static", filename=f"processed_images/{out_name}", _external=True, _scheme="https")

def _save_gcs(img: Image.Image, out_name: str) -> str:
    bucket = gcs_client.bucket(GCS_BUCKET)
    blob = bucket.blob(f"{GCS_PREFIX}/{out_name}")

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95, optimize=True)
    buf.seek(0)
    blob.upload_from_file(buf, content_type="image/jpeg")

    if SIGNED_SECS > 0:
        return blob.generate_signed_url(expiration=timedelta(seconds=SIGNED_SECS), version="v4")
    try:
        blob.make_public()
        return blob.public_url
    except Exception:
        return blob.generate_signed_url(expiration=timedelta(days=365), version="v4")

@app.route("/")
def index():
    return "Background Removal API is running!"

@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/remove-bg", methods=["POST"])
def remove_bg():
    file = request.files.get("image")
    if not file or file.filename == "":
        return jsonify({"error": "No image uploaded"}), 400

    safe = secure_filename(file.filename)
    base, _ = os.path.splitext(safe)

    try:
        final_rgb = _remove_bg_and_flatten_to_white(file)

        uniq = uuid.uuid4().hex[:10]
        out_name = f"bg_removed_{base}_{uniq}.jpg"

        if use_gcs:
            image_url = _save_gcs(final_rgb, out_name)
        else:
            image_url = _save_local(final_rgb, out_name)

        return jsonify({"image_url": image_url}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
