from flask import Flask, request, jsonify
import face_recognition
import numpy as np
import base64
import io
from PIL import Image

app = Flask(__name__)

@app.route('/predict', methods=['POST'])
def predict():
    # Expect JSON with base64‑encoded image data
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({"status": "error", "message": "No image provided"}), 400
    try:
        # Decode base64 image
        image_bytes = base64.b64decode(data['image'])
        pil_img = Image.open(io.BytesIO(image_bytes))
        # Convert to numpy array (RGB)
        image_np = np.array(pil_img.convert('RGB'))
        # Use face_recognition to locate faces and compute encodings
        face_locations = face_recognition.face_locations(image_np)
        if not face_locations:
            return jsonify({"status": "not_found", "name": None})
        # For demo, just return the first face found
        return jsonify({"status": "success", "name": "Recognized Person"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # Use port 8000 by default; Render will override with $PORT if needed
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
