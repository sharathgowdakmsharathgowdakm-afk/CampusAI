// Face Registration JavaScript - Premium & Modern UI
// Handles Select2, Live Camera (Webcam + CCTV), Zooming, Automatic 5-Pose Sequence, and Face Registration.

let videoStream = null;
let capturedPoses = []; // Array of Base64 strings (max 5)
let currentMode = 'upload'; // 'upload' or 'camera'
let currentCameraType = 'local'; // 'local' or 'cctv'
let currentZoom = 1.0;
const MIN_ZOOM = 1.0;
const MAX_ZOOM = 3.0;

let isAutoCapturing = false;

const POSES = [
  { name: "Look Straight", icon: "fa-smile", instruction: "Pose 1 of 5: Look Straight at Camera" },
  { name: "Look Slightly Left", icon: "fa-arrow-left", instruction: "Pose 2 of 5: Turn Head Slightly Left" },
  { name: "Look Slightly Right", icon: "fa-arrow-right", instruction: "Pose 3 of 5: Turn Head Slightly Right" },
  { name: "Look Slightly Up", icon: "fa-arrow-up", instruction: "Pose 4 of 5: Tilt Head Slightly Up" },
  { name: "Look Slightly Down", icon: "fa-arrow-down", instruction: "Pose 5 of 5: Tilt Head Slightly Down / Smile" }
];

// DOM Elements
const classSelect = document.getElementById('classSelect');
const studentSelect = document.getElementById('studentSelect');
const studentStatus = document.getElementById('studentStatus');

const btnUploadMode = document.getElementById('btnUploadMode');
const btnCameraMode = document.getElementById('btnCameraMode');

const uploadSection = document.getElementById('uploadSection');
const cameraSection = document.getElementById('cameraSection');

const poseBanner = document.getElementById('poseBanner');
const poseTitle = document.getElementById('poseTitle');
const poseCountdown = document.getElementById('poseCountdown');
const startAutoCaptureBtn = document.getElementById('startAutoCaptureBtn');
const cameraFlash = document.getElementById('cameraFlash');

const camLocalRadio = document.getElementById('camLocal');
const camCctvRadio = document.getElementById('camCctv');
const localCamWrapper = document.getElementById('localCamWrapper');
const cctvWrapper = document.getElementById('cctvWrapper');
const deviceSelect = document.getElementById('deviceSelect');
const cctvUrlInput = document.getElementById('cctvUrlInput');
const fetchCctvBtn = document.getElementById('fetchCctvBtn');

const videoFeed = document.getElementById('videoFeed');
const videoZoomWrapper = document.getElementById('videoZoomWrapper');
const zoomOutBtn = document.getElementById('zoomOutBtn');
const zoomInBtn = document.getElementById('zoomInBtn');
const zoomSlider = document.getElementById('zoomSlider');
const zoomLabel = document.getElementById('zoomLabel');

const captureBtn = document.getElementById('captureBtn');
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');

const posesBadge = document.getElementById('posesBadge');
const poseGallery = document.getElementById('poseGallery');
const clearPosesBtn = document.getElementById('clearPosesBtn');
const submitBtn = document.getElementById('submitBtn');

const loadingOverlay = document.getElementById('loadingOverlay');
const resultCard = document.getElementById('resultCard');
const resultMsg = document.getElementById('resultMsg');
const errorAlert = document.getElementById('errorAlert');

// ─── Initialize Select2 with jQuery & Event Listeners ───────────────────────
if (window.$ && $.fn.select2) {
  $(document).ready(() => {
    $('#classSelect').select2({ theme: 'bootstrap-5', placeholder: 'Select class', allowClear: true });
    $('#studentSelect').select2({ theme: 'bootstrap-5', placeholder: 'Select student' });

    $('#classSelect').on('change', function () {
      filterStudentsByClass(this.value);
    });

    $('#studentSelect').on('change', function () {
      checkStudentFaceStatus();
      validateForm();
    });
  });
} else {
  classSelect && classSelect.addEventListener('change', function () {
    filterStudentsByClass(this.value);
  });
  studentSelect && studentSelect.addEventListener('change', () => {
    checkStudentFaceStatus();
    validateForm();
  });
}

function filterStudentsByClass(classId) {
  if (!studentSelect) return;
  if (window.$ && $.fn.select2) {
    $('#studentSelect').val('').trigger('change');
  } else {
    studentSelect.value = '';
  }
  const options = studentSelect.querySelectorAll('option[data-class-id]');
  options.forEach(opt => {
    opt.style.display = (!classId || opt.dataset.classId === classId) ? '' : 'none';
  });
}

// ─── Face Status Check ───────────────────────────────────────────────────────
function checkStudentFaceStatus() {
  const studentId = studentSelect ? studentSelect.value : '';
  if (!studentStatus) return;
  studentStatus.innerHTML = '';
  if (!studentId) return;

  const url = `/school/api/student/${studentId}/face-status`;
  fetch(url)
    .then(r => r.json())
    .then(d => {
      if (d.has_face) {
        studentStatus.innerHTML = `<span class="badge bg-success py-2 px-3 fs-6"><i class="fas fa-check-circle me-1"></i> Face Registered (${d.encoding_count} encoding${d.encoding_count !== 1 ? 's' : ''})</span>`;
      } else {
        studentStatus.innerHTML = `<span class="badge bg-warning text-dark py-2 px-3 fs-6"><i class="fas fa-exclamation-circle me-1"></i> No Face Data Registered</span>`;
      }
    })
    .catch(err => console.log('Face status fetch error:', err));
}

// ─── Mode Switch (Upload vs Camera) ──────────────────────────────────────────
btnUploadMode && btnUploadMode.addEventListener('click', () => switchMode('upload'));
btnCameraMode && btnCameraMode.addEventListener('click', () => switchMode('camera'));

function switchMode(mode) {
  stopAutoCapture();
  currentMode = mode;
  btnUploadMode.classList.toggle('active', mode === 'upload');
  btnCameraMode.classList.toggle('active', mode === 'camera');

  if (mode === 'camera') {
    cameraSection.classList.remove('d-none');
    uploadSection.classList.add('d-none');
    if (currentCameraType === 'local') {
      enumerateDevices();
      startCamera();
    }
  } else {
    cameraSection.classList.add('d-none');
    uploadSection.classList.remove('d-none');
    stopCamera();
  }
}

// ─── Camera Type Switch (Local Device vs CCTV) ──────────────────────────────
camLocalRadio && camLocalRadio.addEventListener('change', () => switchCameraType('local'));
camCctvRadio && camCctvRadio.addEventListener('change', () => switchCameraType('cctv'));

function switchCameraType(type) {
  stopAutoCapture();
  currentCameraType = type;
  if (type === 'local') {
    localCamWrapper.classList.remove('d-none');
    cctvWrapper.classList.add('d-none');
    enumerateDevices();
    startCamera();
  } else {
    localCamWrapper.classList.add('d-none');
    cctvWrapper.classList.remove('d-none');
    stopCamera();
  }
}

// ─── Camera Device Enumeration & Controls ────────────────────────────────────
async function enumerateDevices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices || !deviceSelect) return;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(d => d.kind === 'videoinput');
    deviceSelect.innerHTML = '';
    videoDevices.forEach((dev, i) => {
      const opt = document.createElement('option');
      opt.value = dev.deviceId;
      opt.textContent = dev.label || `Camera ${i + 1}`;
      deviceSelect.appendChild(opt);
    });
  } catch (e) {
    console.warn('Device enumeration failed', e);
  }
}

deviceSelect && deviceSelect.addEventListener('change', () => {
  stopCamera();
  startCamera(deviceSelect.value);
});

function startCamera(deviceId) {
  if (currentCameraType !== 'local') return;

  const constraints = {
    video: {
      width: { ideal: 1280 },
      height: { ideal: 720 }
    }
  };
  if (deviceId) {
    constraints.video.deviceId = { exact: deviceId };
  } else {
    constraints.video.facingMode = 'user';
  }

  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia(constraints)
      .then(stream => {
        videoStream = stream;
        videoFeed.srcObject = stream;
        videoFeed.style.display = 'block';
        currentZoom = 1.0;
        applyZoom();
      })
      .catch(err => {
        showError('Camera access denied or device unavailable. You can use Upload mode or CCTV Camera.');
      });
  } else {
    showError('Camera API not accessible on HTTP. Use localhost, HTTPS, or CCTV Camera option.');
  }
}

function stopCamera() {
  stopAutoCapture();
  if (videoStream) {
    videoStream.getTracks().forEach(t => t.stop());
    videoStream = null;
  }
}

// ─── Zoom Controls ───────────────────────────────────────────────────────────
function applyZoom() {
  if (videoFeed) videoFeed.style.transform = `scale(${currentZoom})`;
  if (zoomSlider) zoomSlider.value = currentZoom;
  if (zoomLabel) zoomLabel.textContent = `${currentZoom.toFixed(1)}x`;
}

zoomSlider && zoomSlider.addEventListener('input', e => {
  currentZoom = parseFloat(e.target.value);
  applyZoom();
});
zoomInBtn && zoomInBtn.addEventListener('click', () => {
  currentZoom = Math.min(MAX_ZOOM, currentZoom + 0.2);
  applyZoom();
});
zoomOutBtn && zoomOutBtn.addEventListener('click', () => {
  currentZoom = Math.max(MIN_ZOOM, currentZoom - 0.2);
  applyZoom();
});

videoZoomWrapper && videoZoomWrapper.addEventListener('wheel', e => {
  e.preventDefault();
  const delta = -e.deltaY * 0.001;
  currentZoom = Math.min(Math.max(MIN_ZOOM, currentZoom + delta), MAX_ZOOM);
  applyZoom();
});

// ─── Visual Flash Animation ──────────────────────────────────────────────────
function triggerFlash() {
  if (!cameraFlash) return;
  cameraFlash.classList.add('flash-active');
  setTimeout(() => cameraFlash.classList.remove('flash-active'), 250);
}

// ─── Automatic 5-Pose Capture Sequence ───────────────────────────────────────
startAutoCaptureBtn && startAutoCaptureBtn.addEventListener('click', startAutoCaptureSequence);

async function startAutoCaptureSequence() {
  if (isAutoCapturing) return;

  if (currentCameraType === 'local' && (!videoFeed || !videoFeed.videoWidth)) {
    showError('Camera feed is initializing. Please wait a moment.');
    return;
  }
  if (currentCameraType === 'cctv') {
    const url = cctvUrlInput ? cctvUrlInput.value.trim() : '';
    if (!url) {
      showError('Please enter a valid CCTV stream URL before starting auto capture.');
      return;
    }
  }

  isAutoCapturing = true;
  capturedPoses = []; // reset for clean sequence
  renderPoseGallery();
  validateForm();

  if (startAutoCaptureBtn) {
    startAutoCaptureBtn.disabled = true;
    startAutoCaptureBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Auto Capturing...';
  }

  for (let i = 0; i < POSES.length; i++) {
    if (!isAutoCapturing) break;

    const pose = POSES[i];

    // 1. Update Top Banner Heading
    if (poseTitle) {
      poseTitle.innerHTML = `<i class="fas ${pose.icon} text-primary me-2"></i>${pose.instruction}`;
    }

    // 2. Countdown 2 Seconds per Pose
    for (let count = 2; count > 0; count--) {
      if (!isAutoCapturing) break;
      if (poseCountdown) {
        poseCountdown.innerHTML = `<span class="badge bg-primary fs-6 me-2">${count}s</span> Position yourself: <strong>${pose.name}</strong>...`;
      }
      await delay(1000);
    }

    if (!isAutoCapturing) break;

    // 3. Capture Frame
    if (currentCameraType === 'local') {
      triggerFlash();
      const canvas = document.createElement('canvas');
      canvas.width = videoFeed.videoWidth;
      canvas.height = videoFeed.videoHeight;
      const ctx = canvas.getContext('2d');

      const w = canvas.width;
      const h = canvas.height;
      const sx = (w - w / currentZoom) / 2;
      const sy = (h - h / currentZoom) / 2;
      const sw = w / currentZoom;
      const sh = h / currentZoom;
      ctx.drawImage(videoFeed, sx, sy, sw, sh, 0, 0, w, h);

      const b64 = canvas.toDataURL('image/jpeg', 0.9);
      addPose(b64);
    } else if (currentCameraType === 'cctv') {
      triggerFlash();
      if (poseCountdown) poseCountdown.innerHTML = `<i class="fas fa-spinner fa-spin me-1"></i> Fetching CCTV frame (${pose.name})...`;
      const url = cctvUrlInput.value.trim();
      try {
        const res = await fetch('/capture-cctv', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: url })
        });
        const data = await res.json();
        if (data.success && data.image) {
          addPose(data.image);
        } else {
          showError(`CCTV Frame ${i + 1} capture failed: ${data.error || 'No image'}`);
        }
      } catch (e) {
        showError(`CCTV Connection error on pose ${i + 1}`);
      }
    }

    await delay(600);
  }

  isAutoCapturing = false;

  if (startAutoCaptureBtn) {
    startAutoCaptureBtn.disabled = false;
    startAutoCaptureBtn.innerHTML = '<i class="fas fa-redo me-2"></i>Recapture 5 Poses';
  }

  if (capturedPoses.length >= 5) {
    if (poseTitle) poseTitle.innerHTML = `<i class="fas fa-check-circle text-success me-2"></i>All 5 Poses Captured Successfully!`;
    if (poseCountdown) poseCountdown.innerHTML = `Click "Register Face" button below to submit encodings.`;
  }
}

function stopAutoCapture() {
  isAutoCapturing = false;
  if (startAutoCaptureBtn) {
    startAutoCaptureBtn.disabled = false;
    startAutoCaptureBtn.innerHTML = '<i class="fas fa-magic me-2"></i>Start Auto 5-Pose Capture';
  }
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ─── Single Pose Manual Capture ──────────────────────────────────────────────
captureBtn && captureBtn.addEventListener('click', () => {
  if (capturedPoses.length >= 5) {
    showError('Maximum 5 poses captured. Delete a pose or register now.');
    return;
  }
  if (!videoFeed || !videoFeed.videoWidth) {
    showError('Live camera feed is not ready.');
    return;
  }

  triggerFlash();
  const canvas = document.createElement('canvas');
  canvas.width = videoFeed.videoWidth;
  canvas.height = videoFeed.videoHeight;
  const ctx = canvas.getContext('2d');

  const w = canvas.width;
  const h = canvas.height;
  const sx = (w - w / currentZoom) / 2;
  const sy = (h - h / currentZoom) / 2;
  const sw = w / currentZoom;
  const sh = h / currentZoom;
  ctx.drawImage(videoFeed, sx, sy, sw, sh, 0, 0, w, h);

  const base64Data = canvas.toDataURL('image/jpeg', 0.9);
  addPose(base64Data);
});

// ─── CCTV Camera Single Frame Capture ────────────────────────────────────────
fetchCctvBtn && fetchCctvBtn.addEventListener('click', async () => {
  if (capturedPoses.length >= 5) {
    showError('Maximum 5 poses captured. Delete a pose or register now.');
    return;
  }
  const url = cctvUrlInput ? cctvUrlInput.value.trim() : '';
  if (!url) {
    showError('Please enter a valid CCTV stream URL or camera index (e.g., rtsp://... or 0).');
    return;
  }

  fetchCctvBtn.disabled = true;
  fetchCctvBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Fetching...';

  try {
    const res = await fetch('/capture-cctv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url })
    });
    const data = await res.json();
    fetchCctvBtn.disabled = false;
    fetchCctvBtn.innerHTML = '<i class="fas fa-camera me-1"></i> Fetch CCTV Frame';

    if (data.success && data.image) {
      triggerFlash();
      addPose(data.image);
    } else {
      showError(data.error || 'Failed to capture frame from CCTV.');
    }
  } catch (err) {
    fetchCctvBtn.disabled = false;
    fetchCctvBtn.innerHTML = '<i class="fas fa-camera me-1"></i> Fetch CCTV Frame';
    showError('Error connecting to CCTV server: ' + err.message);
  }
});

// ─── Upload Handling ─────────────────────────────────────────────────────────
if (dropZone) {
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  });
}
fileInput && fileInput.addEventListener('change', e => {
  if (e.target.files.length) handleFiles(e.target.files);
});

function handleFiles(files) {
  Array.from(files).forEach(file => {
    if (capturedPoses.length >= 5) return;
    if (!file.type.startsWith('image/')) {
      showError('Please select valid image files (JPG/PNG).');
      return;
    }
    const reader = new FileReader();
    reader.onload = ev => {
      addPose(ev.target.result);
    };
    reader.readAsDataURL(file);
  });
}

// ─── Pose Gallery Management ──────────────────────────────────────────────────
function addPose(base64Data) {
  if (capturedPoses.length >= 5) return;
  capturedPoses.push(base64Data);
  renderPoseGallery();
  validateForm();
}

function removePose(index) {
  capturedPoses.splice(index, 1);
  renderPoseGallery();
  validateForm();
}

clearPosesBtn && clearPosesBtn.addEventListener('click', () => {
  stopAutoCapture();
  capturedPoses = [];
  renderPoseGallery();
  validateForm();
  if (poseTitle) poseTitle.innerHTML = `<i class="fas fa-camera text-primary me-2"></i>Pose 1 of 5: Look Straight at Camera`;
  if (poseCountdown) poseCountdown.innerHTML = `Click "Start Auto 5-Pose Capture" to capture 5 photos automatically.`;
});

function renderPoseGallery() {
  if (!poseGallery || !posesBadge) return;
  poseGallery.innerHTML = '';
  posesBadge.textContent = `${capturedPoses.length} / 5 Poses Captured`;
  posesBadge.className = capturedPoses.length > 0 ? 'badge bg-primary py-2 px-3' : 'badge bg-secondary py-2 px-3';

  if (capturedPoses.length === 0) {
    poseGallery.innerHTML = '<div class="text-muted small italic text-center w-100 py-3">No poses captured yet. Click "Start Auto 5-Pose Capture" to capture 5 photos automatically.</div>';
    clearPosesBtn.classList.add('d-none');
    return;
  }

  clearPosesBtn.classList.remove('d-none');

  capturedPoses.forEach((b64, idx) => {
    const poseName = POSES[idx] ? POSES[idx].name : `Pose ${idx + 1}`;
    const col = document.createElement('div');
    col.className = 'pose-card-wrapper';
    col.innerHTML = `
      <div class="pose-card position-relative border rounded shadow-sm overflow-hidden bg-dark">
        <img src="${b64}" class="w-100" style="height:120px; object-fit:cover;" alt="Pose ${idx + 1}">
        <span class="badge bg-dark bg-opacity-75 position-absolute top-0 start-0 m-1 text-white">${poseName}</span>
        <button type="button" class="btn btn-danger btn-sm position-absolute top-0 end-0 m-1 rounded-circle p-0 d-flex align-items-center justify-content-center" style="width:24px; height:24px;" onclick="removePose(${idx})">
          <i class="fas fa-times"></i>
        </button>
      </div>
    `;
    poseGallery.appendChild(col);
  });
}

window.removePose = removePose;

// ─── Form Validation ─────────────────────────────────────────────────────────
function validateForm() {
  const sid = studentSelect ? studentSelect.value : '';
  const hasStudent = !!sid;
  const hasPoses = capturedPoses.length > 0;

  if (submitBtn) {
    submitBtn.disabled = !(hasStudent && hasPoses);
    if (hasPoses) {
      submitBtn.innerHTML = `<i class="fas fa-user-check me-2"></i>Register Face (${capturedPoses.length} Pose${capturedPoses.length > 1 ? 's' : ''})`;
    } else {
      submitBtn.innerHTML = `<i class="fas fa-user-check me-2"></i>Register Face`;
    }
  }
}

// ─── Error Alert Helper ──────────────────────────────────────────────────────
function showError(msg) {
  if (!errorAlert) return;
  errorAlert.textContent = msg;
  errorAlert.classList.remove('d-none');
  setTimeout(() => errorAlert.classList.add('d-none'), 6000);
}

// ─── Submit Registration ─────────────────────────────────────────────────────
submitBtn && submitBtn.addEventListener('click', () => {
  const sid = studentSelect ? studentSelect.value : '';
  if (!sid || capturedPoses.length === 0) return;

  errorAlert && errorAlert.classList.add('d-none');
  resultCard && resultCard.classList.add('d-none');
  loadingOverlay && loadingOverlay.classList.remove('d-none');

  let apiEndpoint = '/school/api/register-face';
  if (window.location.pathname.includes('/college/')) {
    apiEndpoint = '/college/face-register';
  } else if (window.location.pathname.includes('/institution/')) {
    apiEndpoint = '/institution/face-register';
  }

  fetch(apiEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      student_id: sid,
      images_base64: capturedPoses,
      image_base64: capturedPoses[0] // fallback for legacy handlers
    })
  })
    .then(r => r.json())
    .then(d => {
      loadingOverlay && loadingOverlay.classList.add('d-none');
      if (d.success || d.message) {
        if (resultMsg) resultMsg.textContent = d.message || d.success || 'Face encodings registered successfully!';
        resultCard && resultCard.classList.remove('d-none');
        checkStudentFaceStatus();
        capturedPoses = [];
        renderPoseGallery();
        validateForm();
        setTimeout(() => resultCard && resultCard.classList.add('d-none'), 6000);
      } else {
        showError(d.error || 'Registration failed.');
      }
    })
    .catch(err => {
      console.error(err);
      loadingOverlay && loadingOverlay.classList.add('d-none');
      showError('Network error. Please try again.');
    });
});

// ─── Lifecycle ───────────────────────────────────────────────────────────────
window.addEventListener('beforeunload', stopCamera);
