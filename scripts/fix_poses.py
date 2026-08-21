import os
import re

files = [
    'templates/college/face_register.html',
    'templates/institution/face_register.html',
    'templates/school/face_register.html'
]

for filepath in files:
    if not os.path.exists(filepath):
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    org = filepath.split('/')[1]
    
    content = re.sub(
        r'(<video id="videoFeed" autoplay playsinline muted></video>\s*<canvas id="captureCanvas"></canvas>)',
        r'<div id="poseInstruction" class="alert alert-info text-center fw-bold mt-2" style="display:none; font-size:1.2rem;"></div>\n                    \1',
        content
    )
    
    content = content.replace(
        '<button class="capture-btn" id="captureBtn" onclick="capturePhoto()"><i class="fas fa-camera"></i></button>',
        '<button class="capture-btn" id="captureBtn" onclick="startMultiCapture()"><i class="fas fa-camera"></i></button>'
    )
    
    content = content.replace(
        '<span id="captureStatus" class="status-badge badge-empty"><i class="fas fa-circle-xmark"></i> No photo yet</span>',
        '<span id="captureStatus" class="status-badge badge-empty"><i class="fas fa-circle-xmark"></i> 0/5 Poses</span>'
    )
    
    content = content.replace(
        'let stream=null,capturedBlob=null,currentMode=null;',
        'let stream=null,capturedBlobs=[],currentMode=null;\nconst poses = ["Look Straight", "Look Slightly Left", "Look Slightly Right", "Look Slightly Up", "Look Slightly Down"];'
    )
    
    old_registerFace = f"async function registerFace(){{const studentId=document.getElementById('studentSelect').value;if(!studentId){{showResult('Please select a student.',false);return;}}if(!currentMode){{showResult('Please choose Camera or Upload option.',false);return;}}let imageBlob;if(currentMode==='camera'){{if(!capturedBlob){{showResult('Please capture a photo first.',false);return;}}imageBlob=capturedBlob;}}else{{const fi=document.getElementById('fileInput');if(!fi.files.length){{showResult('Please select an image file.',false);return;}}imageBlob=fi.files[0];}}const fd=new FormData();fd.append('csrf_token','{{{{ csrf_token() }}}}');fd.append('student_id',studentId);fd.append('face_image',imageBlob,'face.jpg');document.getElementById('spinnerOverlay').classList.add('active');try{{const res=await fetch('/{org}/face-register',{{method:'POST',body:fd}});const data=await res.json();document.getElementById('spinnerOverlay').classList.remove('active');if(data.success){{showResult('✅ '+data.success,true);document.getElementById('studentSelect').value='';capturedBlob=null;}}else{{showResult('❌ Error: '+data.error,false);}}}}catch(err){{document.getElementById('spinnerOverlay').classList.remove('active');showResult('❌ Network error: '+err.message,false);}}}}"
    
    new_registerFace = f"async function registerFace(){{const studentId=document.getElementById('studentSelect').value;if(!studentId){{showResult('Please select a student.',false);return;}}if(!currentMode){{showResult('Please choose Camera or Upload option.',false);return;}}let imageBlobs=[];if(currentMode==='camera'){{if(capturedBlobs.length < 5){{showResult('Please capture all 5 photos first.',false);return;}}imageBlobs=capturedBlobs;}}else{{const fi=document.getElementById('fileInput');if(!fi.files.length){{showResult('Please select an image file.',false);return;}}imageBlobs=[fi.files[0]];}}const fd=new FormData();fd.append('csrf_token','{{{{ csrf_token() }}}}');fd.append('student_id',studentId);imageBlobs.forEach((blob,i)=>fd.append('face_images',blob,`face_${{i}}.jpg`));document.getElementById('spinnerOverlay').classList.add('active');try{{const res=await fetch('/{org}/face-register',{{method:'POST',body:fd}});const data=await res.json();document.getElementById('spinnerOverlay').classList.remove('active');if(data.success){{showResult('✅ '+data.success,true);document.getElementById('studentSelect').value='';capturedBlobs=[];}}else{{showResult('❌ Error: '+data.error,false);}}}}catch(err){{document.getElementById('spinnerOverlay').classList.remove('active');showResult('❌ Network error: '+err.message,false);}}}}"
    
    content = content.replace(old_registerFace, new_registerFace)
    
    content = content.replace(
'''        capturedBlob = null;
        document.getElementById('captureStatus').className = 'status-badge badge-empty';
        document.getElementById('captureStatus').innerHTML = '<i class="fas fa-circle-xmark"></i> No photo yet';
        document.getElementById('retakeBtn').style.display = 'none';
        document.getElementById('captureBtn').style.display = 'inline-block';''',
'''        capturedBlobs = [];
        document.getElementById('captureStatus').className = 'status-badge badge-empty';
        document.getElementById('captureStatus').innerHTML = '<i class="fas fa-circle-xmark"></i> 0/5 Poses';
        document.getElementById('retakeBtn').style.display = 'none';
        document.getElementById('captureBtn').style.display = 'inline-block';
        if(document.getElementById('poseInstruction')) document.getElementById('poseInstruction').style.display = 'none';'''
    )
    
    content = content.replace(
'''            capturedBlob = blob;
            
            statusBadge.className = 'status-badge badge-ready';
            statusBadge.innerHTML = '<i class="fas fa-check-circle"></i> CCTV Capture Successful';''',
'''            capturedBlobs = [blob, blob, blob, blob, blob];
            
            statusBadge.className = 'status-badge badge-ready';
            statusBadge.innerHTML = '<i class="fas fa-check-circle"></i> CCTV Capture Successful (5/5)';'''
    )
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Fixed {filepath}")
