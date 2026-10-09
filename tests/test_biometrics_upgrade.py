"""
End-to-end Integration Test Suite for CampusAI Biometric Upgrade (SCRFD + ArcFace)
Tests:
- Detection & Landmark Alignment
- Quality Filtering
- ArcFace 512-d Normalization
- Scoped Multi-Tenant Isolation
- Class-Wise Recognition across 3 Classes
- Cosine Similarity Matching & Calibration
- System Diagnostics & Migration Status
"""
import os
import unittest
import numpy as np
import pickle

from face_api.config import (
    FACE_DETECTION_THRESHOLD,
    FACE_RECOGNITION_THRESHOLD,
    EMBEDDING_DIM
)
from face_api.pipeline import get_pipeline
from face_api.matcher import NumPyCosineMatcher
from face_api.detector import DetectedFace


class TestCampusAIBiometrics(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pipeline = get_pipeline()

    def test_pipeline_initialization(self):
        self.assertIsNotNone(self.pipeline.detector)
        self.assertIsNotNone(self.pipeline.recognizer)
        self.assertIsNotNone(self.pipeline.quality_filter)
        self.assertIsNotNone(self.pipeline.embedding_store)
        diag = self.pipeline.get_diagnostics()
        self.assertEqual(diag["face_detector"], "SCRFD (det_10g)")
        self.assertEqual(diag["face_recognizer"], "ArcFace (w600k_r50)")
        self.assertTrue(diag["models_loaded"])

    def test_detection_and_embedding_extraction(self):
        uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
        test_img_path = os.path.join(uploads_dir, "face_0.jpg")
        if not os.path.exists(test_img_path):
            test_img_path = os.path.join(uploads_dir, "face.jpg")

        if os.path.exists(test_img_path):
            from face_api.pipeline import decode_image
            img = decode_image(test_img_path)
            self.assertIsNotNone(img)

            faces = self.pipeline.detector.detect(img)
            self.assertGreater(len(faces), 0, "SCRFD should detect at least 1 face in sample image")
            face = faces[0]
            self.assertEqual(face.landmarks.shape, (5, 2), "SCRFD should produce 5 facial keypoints")

            q = self.pipeline.quality_filter.evaluate(img, face)
            self.assertTrue(q.is_valid, f"Quality filter should accept sample face, got {q.reason}")

            emb = self.pipeline.recognizer.extract_embedding(img, face.landmarks)
            self.assertEqual(emb.shape, (EMBEDDING_DIM,), f"Embedding must be {EMBEDDING_DIM}-dimensional")
            # Verify unit length L2 norm
            norm = np.linalg.norm(emb)
            self.assertAlmostEqual(norm, 1.0, places=4, msg="ArcFace embedding must be normalized to unit length")

    def test_quality_filter_rejection(self):
        # Create very small low quality image
        small_img = np.zeros((20, 20, 3), dtype=np.uint8)
        dummy_face = DetectedFace(bbox=np.array([0, 0, 15, 15]), score=0.3, landmarks=np.zeros((5, 2)))
        q = self.pipeline.quality_filter.evaluate(small_img, dummy_face)
        self.assertFalse(q.is_valid)
        self.assertIn(q.reason, ["Face too small", "Low detection confidence", "Poor lighting", "Low image quality"])

    def test_cosine_similarity_matcher(self):
        # 10 synthetic 512-d normalized embeddings
        np.random.seed(42)
        gallery = np.random.randn(10, 512).astype(np.float32)
        gallery = gallery / np.linalg.norm(gallery, axis=1, keepdims=True)
        metadata = [{"student_id": i+1, "name": f"Student {i+1}", "roll_number": f"00{i+1}"} for i in range(10)]

        matcher = NumPyCosineMatcher(gallery, metadata, threshold=0.42)

        # Query embedding identical to gallery[3]
        query = gallery[3]
        result = matcher.search(query)
        self.assertTrue(result.is_recognized)
        self.assertEqual(result.student_id, 4, "Cosine matcher should identify student_id 4")
        self.assertAlmostEqual(result.similarity, 1.0, places=3, msg="Identical vector cosine similarity should be ~1.0")

        # Query orthogonal / distant vector
        random_query = np.random.randn(512).astype(np.float32)
        random_query = random_query / np.linalg.norm(random_query)
        max_dot = np.max(np.dot(gallery, random_query))
        if max_dot < 0.42:
            rand_result = matcher.search(random_query)
            self.assertFalse(rand_result.is_recognized, "Unmatched face should be classified as Unknown")

    def test_multi_tenant_isolation(self):
        """Ensure search never crosses organization boundaries."""
        from app import app, db
        with app.app_context():
            store = self.pipeline.embedding_store
            m1 = store.get_matcher(db.session, organization_id=1, force_reload=True)
            m2 = store.get_matcher(db.session, organization_id=2, force_reload=True)

            org1_sids = {item["student_id"] for item in m1.metadata}
            org2_sids = {item["student_id"] for item in m2.metadata}

            intersection = org1_sids.intersection(org2_sids)
            self.assertEqual(len(intersection), 0, "No student ID should bleed across different organization IDs")

    def test_class_wise_isolation_three_classes(self):
        """Verify strict class-wise isolation for Class 1, Class 3, and Class 5."""
        from app import app, db, FaceEncoding
        with app.app_context():
            store = self.pipeline.embedding_store

            # Load matchers for each class
            m_class1 = store.get_matcher(db.session, organization_id=1, class_id=1, force_reload=True)
            m_class3 = store.get_matcher(db.session, organization_id=1, class_id=3, force_reload=True)
            m_class5 = store.get_matcher(db.session, organization_id=1, class_id=5, force_reload=True)

            # Test Student 6 (Shivaputra) registered ONLY in Class 1
            e6 = FaceEncoding.query.filter_by(student_id=6).first()
            if e6 and e6.encoding_path and os.path.exists(e6.encoding_path):
                arr6 = pickle.load(open(e6.encoding_path, 'rb')).astype(np.float64)

                res1 = m_class1.match_face(enc_128=arr6)
                self.assertTrue(res1.is_recognized, "Student 6 must be recognized in Class 1")
                self.assertEqual(res1.student_id, 6)

                res3 = m_class3.match_face(enc_128=arr6)
                self.assertFalse(res3.is_recognized, "Student 6 must NOT be recognized in Class 3 (Unknown)")

                res5 = m_class5.match_face(enc_128=arr6)
                self.assertFalse(res5.is_recognized, "Student 6 must NOT be recognized in Class 5 (Unknown)")

            # Test Student 21 (Jeevitha) registered ONLY in Class 5
            e21 = FaceEncoding.query.filter_by(student_id=21).first()
            if e21 and e21.encoding_path and os.path.exists(e21.encoding_path):
                arr21 = pickle.load(open(e21.encoding_path, 'rb')).astype(np.float64)

                res5 = m_class5.match_face(enc_128=arr21)
                self.assertTrue(res5.is_recognized, "Student 21 must be recognized in Class 5")
                self.assertEqual(res5.student_id, 21)

                res1 = m_class1.match_face(enc_128=arr21)
                self.assertFalse(res1.is_recognized, "Student 21 must NOT be recognized in Class 1 (Unknown)")

                res3 = m_class3.match_face(enc_128=arr21)
                self.assertFalse(res3.is_recognized, "Student 21 must NOT be recognized in Class 3 (Unknown)")


if __name__ == '__main__':
    unittest.main()
