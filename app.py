from flask import Flask, request, jsonify, send_file, url_for
from rembg import remove
from PIL import Image
import io
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

OUTPUT_FOLDER = 'static/processed_images'
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route('/')
def index():
    print(" API Status Checked")
    return " Background Removal API is running!"

@app.route('/remove-bg', methods=['POST'])
def remove_bg():
    print(" POST request received on /remove-bg")

    if 'image' not in request.files:
        print(" No image file in request")
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files['image']
    if file.filename == '':
        print(" Empty filename received")
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    print(f"Uploaded file: {filename}")

    try:
        print(" Loading image...")
        input_image = Image.open(file.stream).convert("RGBA")
        print("Image loaded and converted to RGBA")

        print(" Removing background...")
        output = remove(input_image)
        print(" Background removed")

        print(" Adding white background...")
        background = Image.new("RGBA", output.size, (255, 255, 255, 255))
        background.paste(output, mask=output.split()[3])
        final_image = background.convert("RGB")
        print(" White background added and image converted to RGB")

        # Save final image in OUTPUT_FOLDER
        output_path = os.path.join(OUTPUT_FOLDER, f"bg_removed_{filename}")
        final_image.save(output_path, format='JPEG', quality=100, subsampling=0)
        print(f" Image saved to: {output_path}")

        image_url = url_for('static', filename=f"processed_images/bg_removed_{filename}", _external=True)
        print(f"Returning image URL: {image_url}")

        return jsonify({"image_url": image_url})

    except Exception as e:
        print(f" ERROR: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5000))
    print(f" Starting Flask app on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=True)
