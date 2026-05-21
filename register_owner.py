import cv2
import numpy as np
import os
import time

def register():
    print("=" * 60)
    print("OWNER FACE REGISTRATION (Multi-Sample)")
    print("=" * 60)
    print("\nThis will capture MULTIPLE samples for better recognition.")
    print("You'll need to look at the camera from different angles.\n")
    
    print("Initializing Modern AI models (YuNet + SFace)...")
    
    # 1. Load YuNet (Detection)
    detector = cv2.FaceDetectorYN.create(
        r"C:\security\script\face_detection_yunet_2023mar.onnx",
        "",
        (320, 320),
        0.8,  # Score threshold (slightly lower for better detection)
        0.3,  # NMS threshold
        5000  # Top K
    )

    # 2. Load SFace (Recognition)
    recognizer = cv2.FaceRecognizerSF.create(
        r"C:\security\script\face_recognition_sface_2021dec.onnx",
        ""
    )

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    # Wait for camera to warm up
    time.sleep(0.5)
    for _ in range(10):
        cap.read()

    # Capture multiple samples
    NUM_SAMPLES = 5
    embeddings = []
    reference_frames = []
    
    positions = [
        "CENTER (look straight at camera)",
        "SLIGHT LEFT (turn head slightly left)",
        "SLIGHT RIGHT (turn head slightly right)",
        "SLIGHT UP (tilt head up a bit)",
        "SLIGHT DOWN (tilt head down a bit)"
    ]
    
    for i, position in enumerate(positions):
        print(f"\n[*] Sample {i+1}/{NUM_SAMPLES}: {position}")
        print("   Press ENTER when ready...")
        input()
        
        # Capture multiple frames and pick the best
        best_frame = None
        best_score = 0
        best_face = None
        
        for _ in range(10):  # Try 10 frames
            ret, frame = cap.read()
            if not ret:
                continue
            
            h, w, _ = frame.shape
            detector.setInputSize((w, h))
            _, faces = detector.detect(frame)
            
            if faces is not None:
                for face in faces:
                    score = face[-1]
                    area = face[2] * face[3]
                    combined_score = score * area
                    
                    if combined_score > best_score:
                        best_score = combined_score
                        best_frame = frame.copy()
                        best_face = face
            
            time.sleep(0.05)
        
        if best_face is not None:
            # Extract embedding
            face_align = recognizer.alignCrop(best_frame, best_face)
            face_feature = recognizer.feature(face_align)
            embeddings.append(face_feature)
            reference_frames.append(face_align)
            print(f"   [OK] Captured! (Quality score: {best_face[-1]:.2f})")
        else:
            print(f"   [FAIL] No face detected. Skipping this sample.")
    
    cap.release()
    try:
        cv2.destroyAllWindows()
    except cv2.error:
        pass  # Headless OpenCV build, no windows to destroy
    
    if len(embeddings) < 3:
        print("\n[ERROR] Not enough samples captured (need at least 3)")
        print("   Please try again with better lighting.")
        return
    
    # Average the embeddings for robust recognition
    avg_embedding = np.mean(embeddings, axis=0)
    
    # Normalize the average embedding
    avg_embedding = avg_embedding / np.linalg.norm(avg_embedding)
    
    # Save
    np.save(r"C:\security\script\owner_embedding_sface.npy", avg_embedding)
    print(f"\n[SUCCESS] Owner face registered with {len(embeddings)} samples.")
    print(r"   Embedding saved to C:\security\script\owner_embedding_sface.npy")
    
    # Save best reference image
    if reference_frames:
        cv2.imwrite(r"C:\security\script\owner_ref_sface.jpg", reference_frames[0])
        print(r"   Reference saved to C:\security\script\owner_ref_sface.jpg")
    
    print("\n" + "=" * 60)
    print("TIPS TO IMPROVE RECOGNITION:")
    print("=" * 60)
    print("1. Register in similar lighting conditions as normal use")
    print("2. Remove glasses if you sometimes don't wear them")
    print("3. Keep a neutral expression")
    print("4. Make sure your face is well-lit (avoid backlighting)")
    print("=" * 60)

if __name__ == "__main__":
    register()
