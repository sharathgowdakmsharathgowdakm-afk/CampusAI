import os

html_options = """<!-- CAMERA OPTIONS (PHONE OR CCTV) -->
                    <div class="mb-3 p-3 border rounded bg-light text-dark text-start">
                        <label class="form-label fw-bold d-block text-secondary small text-uppercase mb-2">Camera Source</label>
                        <div class="btn-group w-100 mb-3" role="group">
                            <input type="radio" class="btn-check" name="cameraSourceType" id="srcLocal" value="local" checked onchange="toggleCameraSource()">
                            <label class="btn btn-outline-primary" for="srcLocal"><i class="fas fa-mobile-alt me-2"></i>Phone / Device Camera</label>

                            <input type="radio" class="btn-check" name="cameraSourceType" id="srcCCTV" value="cctv" onchange="toggleCameraSource()">
                            <label class="btn btn-outline-primary" for="srcCCTV"><i class="fas fa-video me-2"></i>CCTV / IP Camera</label>
                        </div>
                        
                        <!-- Local Device Dropdown -->
                        <div id="localCameraSelector">
                            <label class="form-label small text-muted mb-1">Select Device</label>
                            <select id="cameraSourceSelect" class="form-select form-select-sm" onchange="switchLocalCamera()"></select>
                        </div>
                        
                        <!-- CCTV URL Input -->
                        <div id="cctvCameraSelector" style="display: none;">
                            <label class="form-label small text-muted mb-1">CCTV URL / IP Camera Stream</label>
                            <div class="input-group">
                                <input type="text" id="cctvUrlInput" class="form-control form-control-sm" placeholder="rtsp://admin:pass@192.168.1.100:554/h264 or http://...">
                                <button class="btn btn-primary btn-sm" type="button" onclick="captureFromCCTV()">Fetch Frame</button>
                            </div>
                            <small class="text-muted d-block mt-1">Enter your CCTV camera's RTSP or HTTP stream URL.</small>
                        </div>
                    </div>"""

js_face_register_override = """// CCTV and Local Device Switch Overrides
let currentCameraSourceType = 'local';
let localCameraDevices = [];

window.toggleCameraSource = function() {
    const type = document.querySelector('input[name="cameraSourceType"]:checked').value;
    currentCameraSourceType = type;
    
    if (type === 'local') {
        document.getElementById('localCameraSelector').style.display = 'block';
        document.getElementById('cctvCameraSelector').style.display = 'none';
        document.getElementById('videoFeed').style.display = 'block';
        document.getElementById('cameraPreviewBox').style.display = 'none';
        startCamera();
    } else {
        document.getElementById('localCameraSelector').style.display = 'none';
        document.getElementById('cctvCameraSelector').style.display = 'block';
        document.getElementById('videoFeed').style.display = 'none';
        stopCamera();
        
        // Reset state for CCTV
        capturedBlobs = [];
        document.getElementById('captureStatus').className = 'status-badge badge-empty';
        document.getElementById('captureStatus').innerHTML = '<i class="fas fa-circle-xmark"></i> 0/5 Poses';
        document.getElementById('retakeBtn').style.display = 'none';
        document.getElementById('captureBtn').style.display = 'inline-block';
        document.getElementById('poseInstruction').style.display = 'none';
    }
};

window.enumerateCameras = async function() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(device => device.kind === 'videoinput');
        const select = document.getElementById('cameraSourceSelect');
        const currentVal = select.value;
        select.innerHTML = '';
        
        videoDevices.forEach((device, index) => {
            const option = document.createElement('option');
            option.value = device.deviceId;
            option.text = device.label || `Camera ${index + 1}`;
            select.appendChild(option);
        });
        
        if (currentVal && videoDevices.some(d => d.deviceId === currentVal)) {
            select.value = currentVal;
        }
        localCameraDevices = videoDevices;
    } catch (err) {
        console.warn("Could not enumerate cameras: ", err);
    }
};

window.switchLocalCamera = async function() {
    const deviceId = document.getElementById('cameraSourceSelect').value;
    stopCamera();
    startCamera(deviceId);
};

window.startCamera = async function(deviceId = null) {
    if (currentCameraSourceType === 'cctv') return;
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error("Camera API is not supported. Ensure you are using HTTPS or localhost.");
        }
        
        let constraints = { audio: false };
        if (deviceId) {
            constraints.video = { deviceId: { exact: deviceId } };
        } else {
            constraints.video = { facingMode: 'user' };
        }
        
        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (constraintErr) {
            console.warn("Could not access camera with constraints, retrying with generic video stream...", constraintErr);
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        }
        const video = document.getElementById('videoFeed');
        video.srcObject = stream;
        video.style.display = 'block';
        document.getElementById('cameraPreviewBox').style.display = 'none';
        capturedBlobs = [];
        document.getElementById('captureStatus').className = 'status-badge badge-empty';
        document.getElementById('captureStatus').innerHTML = '<i class="fas fa-circle-xmark"></i> 0/5 Poses';
        document.getElementById('retakeBtn').style.display = 'none';
        document.getElementById('captureBtn').style.display = 'inline-block';
        document.getElementById('poseInstruction').style.display = 'none';
        
        await enumerateCameras();
    } catch(e) {
        alert('Could not access camera: ' + e.message + '\\n\\nPlease use the Upload option instead.');
        switchMode('upload');
    }
};

window.startMultiCapture = async function() {
    capturedBlobs = [];
    document.getElementById('captureBtn').style.display = 'none';
    const instr = document.getElementById('poseInstruction');
    instr.style.display = 'block';
    
    for(let i=0; i<5; i++) {
        instr.innerText = poses[i];
        
        let blob;
        if (currentCameraSourceType === 'local') {
            await new Promise(r => setTimeout(r, 1500));
            
            const video = document.getElementById('videoFeed');
            const canvas = document.getElementById('captureCanvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext('2d').drawImage(video, 0, 0);
            
            blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92));
        } else {
            const url = document.getElementById('cctvUrlInput').value.trim();
            if (!url) {
                alert('Please enter a CCTV Stream URL.');
                return;
            }
            
            await new Promise(r => setTimeout(r, 1500));
            
            try {
                const response = await fetch('/capture-cctv', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                const data = await response.json();
                if (data.success) {
                    const base64Response = await fetch(data.image);
                    blob = await base64Response.blob();
                } else {
                    throw new Error(data.error || 'Failed to capture pose');
                }
            } catch (err) {
                alert('CCTV Capture failed: ' + err.message);
                retakePhoto();
                return;
            }
        }
        
        capturedBlobs.push(blob);
        document.getElementById('captureStatus').className = 'status-badge badge-ready';
        document.getElementById('captureStatus').innerHTML = `<i class="fas fa-check-circle"></i> ${i+1}/5 Poses captured`;
    }
    
    instr.innerText = "All poses captured!";
    
    const url = URL.createObjectURL(capturedBlobs[4]);
    document.getElementById('cameraPreviewImg').src = url;
    document.getElementById('cameraPreviewBox').style.display = 'flex';
    document.getElementById('videoFeed').style.display = 'none';
    stopCamera();

    document.getElementById('retakeBtn').style.display = 'inline-flex';
};

window.retakePhoto = function() {
    capturedBlobs = [];
    document.getElementById('cameraPreviewBox').style.display = 'none';
    if (currentCameraSourceType === 'local') {
        document.getElementById('videoFeed').style.display = 'block';
    }
    document.getElementById('retakeBtn').style.display = 'none';
    document.getElementById('captureBtn').style.display = 'inline-block';
    document.getElementById('captureStatus').className = 'status-badge badge-empty';
    document.getElementById('captureStatus').innerHTML = '<i class="fas fa-circle-xmark"></i> 0/5 Poses';
    document.getElementById('poseInstruction').style.display = 'none';
    startCamera();
};

window.captureFromCCTV = async function() {
    const url = document.getElementById('cctvUrlInput').value.trim();
    if (!url) {
        alert('Please enter a CCTV Stream URL.');
        return;
    }
    
    const statusBadge = document.getElementById('captureStatus');
    statusBadge.className = 'status-badge badge-empty';
    statusBadge.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Connecting to CCTV...';
    
    try {
        const response = await fetch('/capture-cctv', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url: url })
        });
        
        const data = await response.json();
        if (data.success) {
            const previewBox = document.getElementById('cameraPreviewBox');
            const previewImg = document.getElementById('cameraPreviewImg');
            previewImg.src = data.image;
            previewBox.style.display = 'flex';
            
            const base64Response = await fetch(data.image);
            const blob = await base64Response.blob();
            capturedBlobs = [blob, blob, blob, blob, blob];
            
            statusBadge.className = 'status-badge badge-ready';
            statusBadge.innerHTML = '<i class="fas fa-check-circle"></i> CCTV Capture Successful (5/5)';
            document.getElementById('retakeBtn').style.display = 'inline-flex';
            document.getElementById('captureBtn').style.display = 'none';
        } else {
            alert('Error from CCTV: ' + (data.error || 'Failed to capture frame'));
            statusBadge.className = 'status-badge badge-empty';
            statusBadge.innerHTML = '<i class="fas fa-circle-xmark"></i> Connection Failed';
        }
    } catch (err) {
        alert('Failed to connect to CCTV: ' + err.message);
        statusBadge.className = 'status-badge badge-empty';
        statusBadge.innerHTML = '<i class="fas fa-circle-xmark"></i> Connection Error';
    }
};"""

js_mark_attendance_override = """// CCTV and Local Device Switch Overrides
let currentCameraSourceType = 'local';
let localCameraDevices = [];

window.toggleCameraSource = function() {
    const type = document.querySelector('input[name="cameraSourceType"]:checked').value;
    currentCameraSourceType = type;
    
    if (type === 'local') {
        document.getElementById('localCameraSelector').style.display = 'block';
        document.getElementById('cctvCameraSelector').style.display = 'none';
        document.getElementById('videoFeed').style.display = 'block';
        document.getElementById('cameraPreviewBox').style.display = 'none';
        startCamera();
    } else {
        document.getElementById('localCameraSelector').style.display = 'none';
        document.getElementById('cctvCameraSelector').style.display = 'block';
        document.getElementById('videoFeed').style.display = 'none';
        stopCamera();
        
        // Reset state for CCTV
        capturedBlob = null;
        document.getElementById('captureStatus').className = 'status-badge badge-empty';
        document.getElementById('captureStatus').innerHTML = '<i class="fas fa-circle-xmark"></i> No photo yet';
        document.getElementById('retakeBtn').style.display = 'none';
    }
};

window.enumerateCameras = async function() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(device => device.kind === 'videoinput');
        const select = document.getElementById('cameraSourceSelect');
        const currentVal = select.value;
        select.innerHTML = '';
        
        videoDevices.forEach((device, index) => {
            const option = document.createElement('option');
            option.value = device.deviceId;
            option.text = device.label || `Camera ${index + 1}`;
            select.appendChild(option);
        });
        
        if (currentVal && videoDevices.some(d => d.deviceId === currentVal)) {
            select.value = currentVal;
        }
        localCameraDevices = videoDevices;
    } catch (err) {
        console.warn("Could not enumerate cameras: ", err);
    }
};

window.switchLocalCamera = async function() {
    const deviceId = document.getElementById('cameraSourceSelect').value;
    stopCamera();
    startCamera(deviceId);
};

window.startCamera = async function(deviceId = null) {
    if (currentCameraSourceType === 'cctv') return;
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error("Camera API is not supported. Ensure you are using HTTPS or localhost.");
        }
        
        let constraints = { audio: false };
        if (deviceId) {
            constraints.video = { deviceId: { exact: deviceId } };
        } else {
            constraints.video = { facingMode: 'environment' };
        }
        
        try {
            stream = await navigator.mediaDevices.getUserMedia(constraints);
        } catch (constraintErr) {
            console.warn("Could not access camera with constraints, retrying with generic video stream...", constraintErr);
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        }
        const video = document.getElementById('videoFeed');
        video.srcObject = stream;
        video.style.display = 'block';
        document.getElementById('cameraPreviewBox').style.display = 'none';
        capturedBlob = null;
        document.getElementById('captureStatus').className = 'status-badge badge-empty';
        document.getElementById('captureStatus').innerHTML = '<i class="fas fa-circle-xmark"></i> No photo yet';
        document.getElementById('retakeBtn').style.display = 'none';
        
        await enumerateCameras();
    } catch(e) {
        alert('Could not access camera: ' + e.message + '\\n\\nPlease use the Upload option instead.');
        switchMode('upload');
    }
};

window.capturePhoto = function() {
    const video = document.getElementById('videoFeed');
    const canvas = document.getElementById('captureCanvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);

    canvas.toBlob(blob => {
        capturedBlob = blob;
        const url = URL.createObjectURL(blob);
        document.getElementById('cameraPreviewImg').src = url;
        document.getElementById('cameraPreviewBox').style.display = 'flex';
        video.style.display = 'none';
        stopCamera();

        document.getElementById('captureStatus').className = 'status-badge badge-ready';
        document.getElementById('captureStatus').innerHTML = '<i class="fas fa-check-circle"></i> Photo captured';
        document.getElementById('retakeBtn').style.display = 'inline-flex';
    }, 'image/jpeg', 0.92);
};

window.retakePhoto = function() {
    capturedBlob = null;
    document.getElementById('cameraPreviewBox').style.display = 'none';
    if (currentCameraSourceType === 'local') {
        document.getElementById('videoFeed').style.display = 'block';
    }
    document.getElementById('retakeBtn').style.display = 'none';
    document.getElementById('captureStatus').className = 'status-badge badge-empty';
    document.getElementById('captureStatus').innerHTML = '<i class="fas fa-circle-xmark"></i> No photo yet';
    startCamera();
};

window.captureFromCCTV = async function() {
    const url = document.getElementById('cctvUrlInput').value.trim();
    if (!url) {
        alert('Please enter a CCTV Stream URL.');
        return;
    }
    
    const statusBadge = document.getElementById('captureStatus');
    statusBadge.className = 'status-badge badge-empty';
    statusBadge.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Connecting to CCTV...';
    
    try {
        const response = await fetch('/capture-cctv', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url: url })
        });
        
        const data = await response.json();
        if (data.success) {
            const previewBox = document.getElementById('cameraPreviewBox');
            const previewImg = document.getElementById('cameraPreviewImg');
            previewImg.src = data.image;
            previewBox.style.display = 'flex';
            
            const base64Response = await fetch(data.image);
            capturedBlob = await base64Response.blob();
            
            statusBadge.className = 'status-badge badge-ready';
            statusBadge.innerHTML = '<i class="fas fa-check-circle"></i> CCTV Frame Captured';
            document.getElementById('retakeBtn').style.display = 'inline-flex';
        } else {
            alert('Error from CCTV: ' + (data.error || 'Failed to capture frame'));
            statusBadge.className = 'status-badge badge-empty';
            statusBadge.innerHTML = '<i class="fas fa-circle-xmark"></i> Connection Failed';
        }
    } catch (err) {
        alert('Failed to connect to CCTV: ' + err.message);
        statusBadge.className = 'status-badge badge-empty';
        statusBadge.innerHTML = '<i class="fas fa-circle-xmark"></i> Connection Error';
    }
};"""

for root, dirs, files in os.walk('templates'):
    for f in files:
        if f in ['face_register.html', 'mark_attendance.html']:
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            modified = False
            
            # 1. Inject HTML Options
            if 'Camera Source' not in content:
                content = content.replace(
                    '<video id="videoFeed"',
                    html_options + '\n                    <video id="videoFeed"'
                )
                modified = True
            
            # 2. Inject JS Override inside extra_js block
            if 'CCTV and Local Device Switch Overrides' not in content:
                if 'face_register' in f:
                    content = content.replace(
                        '</script>\n{% endblock %}',
                        js_face_register_override + '\n</script>\n{% endblock %}'
                    )
                else:
                    content = content.replace(
                        '</script>\n{% endblock %}',
                        js_mark_attendance_override + '\n</script>\n{% endblock %}'
                    )
                modified = True
                
            if modified:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(content)
                print(f'Patched {path}')
print('CCTV Patching completed successfully!')
