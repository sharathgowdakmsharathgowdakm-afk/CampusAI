from flask import Flask, request, jsonify
import numpy as np
import base64
import io
import os
from PIL import Image

# Import SCRFD and ArcFace from face_api package
from face_api.pipeline import get_pipeline

app = Flask(__name__)

@app.route('/predict', methods=['POST'])
def predict():
    """Microservice endpoint to detect faces and extract ArcFace embeddings."""
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({"status": "error", "message": "No image provided"}), 400
    try:
        image_bytes = base64.b64decode(data['image'])
        pil_img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        image_np = np.array(pil_img)

        pipeline = get_pipeline()
        faces = pipeline.detector.detect(image_np)
        if not faces:
            return jsonify({"status": "not_found", "faces_detected": 0})

        results = []
        for face in faces:
            q = pipeline.quality_filter.evaluate(image_np, face)
            emb = pipeline.recognizer.extract_embedding(image_np, face.landmarks) if q.is_valid else None
            results.append({
                "bbox": [int(x) for x in face.bbox],
                "confidence": float(face.confidence),
                "is_valid_quality": q.is_valid,
                "rejection_reason": q.reason,
                "embedding_dim": len(emb) if emb is not None else 0
            })

        return jsonify({
            "status": "success",
            "faces_detected": len(faces),
            "valid_faces": sum(1 for r in results if r["is_valid_quality"]),
            "results": results
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    pipeline = get_pipeline()
    return jsonify(pipeline.get_diagnostics())

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
