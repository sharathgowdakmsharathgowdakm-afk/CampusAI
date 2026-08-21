import os
import re

base_dir = r"c:\Users\shara\OneDrive\Desktop\attendence app\templates"

# Read school template script and html parts
with open(os.path.join(base_dir, "school", "face_register.html"), "r", encoding="utf-8") as f:
    school_content = f.read()

# Extract script
script_match = re.search(r"<script>.*?</script>", school_content, re.DOTALL)
if script_match:
    new_script = script_match.group(0)
    
    # Update college
    college_path = os.path.join(base_dir, "college", "face_register.html")
    with open(college_path, "r", encoding="utf-8") as f:
        college_content = f.read()
    
    college_content = re.sub(r"<script>.*?</script>", new_script.replace("'/school/face-register'", "'/college/face-register'"), college_content, flags=re.DOTALL)
    
    # Also update the camera controls HTML
    camera_controls_html = """
                    <div class="camera-controls mt-3">
                        <button class="retake-btn" id="retakeBtn" onclick="retakePhoto()">
                            <i class="fas fa-redo"></i> Retake
                        </button>
                        <button class="btn btn-primary" id="captureBtn" onclick="startMultiCapture()" style="border-radius:20px; font-weight:bold;">
                            <i class="fas fa-camera"></i> Capture 5 Poses
                        </button>
                        <span id="captureStatus" class="status-badge badge-empty">
                            <i class="fas fa-circle-xmark"></i> 0/5 Poses
                        </span>
                    </div>
                    <div id="poseInstruction" class="text-center mt-2 text-primary fw-bold" style="display:none; font-size:1.1rem;">
                        Look Straight
                    </div>
"""
    college_content = re.sub(r'<div class="camera-controls mt-3">.*?</div>', camera_controls_html.strip(), college_content, flags=re.DOTALL)
    
    # Update file input
    college_content = college_content.replace('<input type="file" id="fileInput" accept="image/*" style="display:none" onchange="handleFileSelect(event)">',
                                              '<input type="file" id="fileInput" accept="image/*" multiple style="display:none" onchange="handleFileSelect(event)">')
                                              
    with open(college_path, "w", encoding="utf-8") as f:
        f.write(college_content)

    # Update institution
    inst_path = os.path.join(base_dir, "institution", "face_register.html")
    with open(inst_path, "r", encoding="utf-8") as f:
        inst_content = f.read()
    
    inst_content = re.sub(r"<script>.*?</script>", new_script.replace("'/school/face-register'", "'/institution/face-register'"), inst_content, flags=re.DOTALL)
    inst_content = re.sub(r'<div class="camera-controls mt-3">.*?</div>', camera_controls_html.strip(), inst_content, flags=re.DOTALL)
    inst_content = inst_content.replace('<input type="file" id="fileInput" accept="image/*" style="display:none" onchange="handleFileSelect(event)">',
                                        '<input type="file" id="fileInput" accept="image/*" multiple style="display:none" onchange="handleFileSelect(event)">')
                                        
    with open(inst_path, "w", encoding="utf-8") as f:
        f.write(inst_content)
        
print("Migration completed.")
