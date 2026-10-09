/**
 * Premium Mark Attendance JavaScript
 * Handles Class Selection, Timetable Subject Auto-Fill,
 * Local/CCTV Camera Capture (1 photo), Photo Upload, and Attendance Submission.
 */

let videoStream = null;
let currentCameraType = 'local'; // 'local' or 'cctv'
let selectedImageBase64 = null;
let currentMode = 'camera'; // 'camera' or 'upload'

// Zoom settings
let currentZoom = 1.0;
const MIN_ZOOM = 1.0;
const MAX_ZOOM = 3.0;

// DOM Elements
const classSelect = document.getElementById('classSelect');
const subjectInput = document.getElementById('subjectInput');
const subjectSelect = document.getElementById('subjectSelect');
const timetableNotice = document.getElementById('timetableNotice');

const btnUploadMode = document.getElementById('btnUploadMode');
const btnCameraMode = document.getElementById('btnCameraMode');
const uploadSection = document.getElementById('uploadSection');
const cameraSection = document.getElementById('cameraSection');

const camLocalRadio = document.getElementById('camLocal');
const camCctvRadio = document.getElementById('camCctv');
const localCamWrapper = document.getElementById('localCamWrapper');
const cctvWrapper = document.getElementById('cctvWrapper');
const deviceSelect = document.getElementById('deviceSelect');
const cctvUrlInput = document.getElementById('cctvUrlInput');
const fetchCctvBtn = document.getElementById('fetchCctvBtn');

const videoZoomWrapper = document.getElementById('videoZoomWrapper');
const videoFeed = document.getElementById('videoFeed');
const cameraFlash = document.getElementById('cameraFlash');
const zoomInBtn = document.getElementById('zoomInBtn');
const zoomOutBtn = document.getElementById('zoomOutBtn');
const zoomSlider = document.getElementById('zoomSlider');
const zoomLabel = document.getElementById('zoomLabel');

const captureBtn = document.getElementById('captureBtn');
const retakeBtn = document.getElementById('retakeBtn');
const cameraPreviewBox = document.getElementById('cameraPreviewBox');
const cameraPreviewImg = document.getElementById('cameraPreviewImg');
const captureCanvas = document.getElementById('captureCanvas') || document.createElement('canvas');

const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const uploadPreviewBox = document.getElementById('uploadPreviewBox');
const uploadPreviewImg = document.getElementById('uploadPreviewImg');
const reselectContainer = document.getElementById('reselectContainer');
const reselectBtn = document.getElementById('reselectBtn');

const submitBtn = document.getElementById('submitBtn');
const loadingOverlay = document.getElementById('loadingOverlay');
const errorAlert = document.getElementById('errorAlert');
const resultSection = document.getElementById('resultSection');
const resultsContainer = document.getElementById('resultsContainer');

// ─── Initialize Select2 & Event Listeners ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (typeof $ !== 'undefined' && $.fn.select2) {
    if (classSelect) $('#classSelect').select2({ theme: 'bootstrap-5' });
    if (subjectSelect) $('#subjectSelect').select2({ theme: 'bootstrap-5' });
  }

  // Handle Class selection change for Timetable Auto-Fill
  if (classSelect) {
    $('#classSelect').on('change', onClassSelected);
    if (!classSelect.value && classSelect.value !== "") {
      onClassSelected();
    }
  }

  // Camera Source Toggle (Local vs CCTV)
  camLocalRadio && camLocalRadio.addEventListener('change', () => switchCameraType('local'));
  camCctvRadio && camCctvRadio.addEventListener('change', () => switchCameraType('cctv'));

  // Device selection change
  deviceSelect && deviceSelect.addEventListener('change', () => {
    if (currentCameraType === 'local') startLocalCamera(deviceSelect.value);
  });

  // Fetch CCTV Frame
  fetchCctvBtn && fetchCctvBtn.addEventListener('click', fetchCctvFrame);

  // Method Toggle (Live Camera vs Upload)
  btnCameraMode && btnCameraMode.addEventListener('click', () => switchMethod('camera'));
  btnUploadMode && btnUploadMode.addEventListener('click', () => switchMethod('upload'));

  // Capture Button (Single Photo)
  captureBtn && captureBtn.addEventListener('click', captureSinglePhoto);
  retakeBtn && retakeBtn.addEventListener('click', resetPhotoCapture);

  // File Upload Handlers
  if (dropZone) {
    dropZone.addEventListener('click', () => fileInput && fileInput.click());
    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length) handleSingleFile(e.dataTransfer.files[0]);
    });
  }

  fileInput && fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) handleSingleFile(e.target.files[0]);
  });
  reselectBtn && reselectBtn.addEventListener('click', () => fileInput && fileInput.click());

  // Submit Button
  submitBtn && submitBtn.addEventListener('click', submitAttendance);

  // Zoom controls
  setupZoomControls();

  // Enumerate cameras
  getDevices();

  // Auto start camera if camera mode is active
  if (currentMode === 'camera') {
    startLocalCamera();
  }

  // Wire up Distance Range Mode radio buttons
  setupDistanceRangeControls();
});

// ─── Distance Range Mode Controls (50m / 100m / Auto) ─────────────────────────
function setupDistanceRangeControls() {
  const distRadios = document.querySelectorAll('input[name="distanceMode"]');
  if (!distRadios.length) return; // Page doesn't have the range panel

  distRadios.forEach(radio => {
    radio.addEventListener('change', () => updateDistanceRangeUI(radio.value));
  });
}

function updateDistanceRangeUI(mode) {
  const badge = document.getElementById('rangeAutoBadge');
  const statusMsg = document.getElementById('rangeStatusMsg');
  const hudVal = document.getElementById('hudDistanceVal');

  if (mode === '50m') {
    if (badge) { badge.textContent = '50m Standard'; badge.className = 'badge bg-primary ms-2 rounded-pill px-2 py-1'; badge.style.fontSize = '0.7rem'; }
    if (statusMsg) statusMsg.textContent = '50m Standard Distance active. Ideal for standard classroom rows up to 50 meters.';
    if (hudVal) { hudVal.textContent = '50m'; hudVal.className = 'text-warning'; }
  } else if (mode === '100m') {
    if (badge) { badge.textContent = '100m Crowd Mode'; badge.className = 'badge bg-success ms-2 rounded-pill px-2 py-1'; badge.style.fontSize = '0.7rem'; }
    if (statusMsg) statusMsg.textContent = '100m Extended Crowd Mode active. Uses high-resolution scanning for large halls, auditoriums, and dense student groups.';
    if (hudVal) { hudVal.textContent = '100m'; hudVal.className = 'text-success'; }
  } else {
    if (badge) { badge.textContent = 'Auto Detect'; badge.className = 'badge bg-info ms-2 rounded-pill px-2 py-1'; badge.style.fontSize = '0.7rem'; }
    if (statusMsg) statusMsg.textContent = 'Auto mode: Distance will be determined by student count. ≤15 students → 50m, >15 students → 100m extended scan.';
    if (hudVal) { hudVal.textContent = 'Auto'; hudVal.className = 'text-info'; }
  }
}

// ─── Auto-Detect Student Count on Class Change ────────────────────────────────
async function autoDetectStudentRange(classId) {
  if (!classId) return;
  try {
    const res = await fetch(`/api/class-students-count/${classId}`);
    const data = await res.json();
    const countNum = document.getElementById('classStudentCountNum');
    const countTag = document.getElementById('classStudentCountTag');

    if (countNum) countNum.textContent = data.student_count || 0;
    if (countTag) countTag.classList.remove('d-none');

    // Auto-select recommended range if in Auto mode
    const autoRadio = document.getElementById('distAuto');
    if (autoRadio && autoRadio.checked) {
      // Auto mode: let backend decide, just update hint
      const hint = data.student_count > 15 ? '100m recommended (large class)' : '50m recommended';
      const statusMsg = document.getElementById('rangeStatusMsg');
      if (statusMsg) statusMsg.textContent = `Auto mode: ${data.student_count} students detected. ${hint}.`;
    }
  } catch (err) {
    console.error('Failed to fetch student count:', err);
  }
}

// ─── Timetable Auto-Fill ──────────────────────────────────────────────────────
async function onClassSelected() {
  const classId = classSelect ? classSelect.value : '';
  validateForm();
  if (!classId) return;

  try {
    const res = await fetch(`/api/timetable/current-subject/${classId}`);
    const data = await res.json();

    if (data.success && data.active_subject) {
      if (subjectInput) {
        subjectInput.value = data.active_subject;
      }
      if (subjectSelect) {
        let exists = Array.from(subjectSelect.options).some(o => o.value === data.active_subject || o.text === data.active_subject);
        if (!exists) {
          const opt = new Option(data.active_subject, data.active_subject, true, true);
          subjectSelect.add(opt);
        }
        $(subjectSelect).val(data.active_subject).trigger('change');
      }

      if (timetableNotice) {
        timetableNotice.classList.remove('d-none');
        timetableNotice.innerHTML = `<i class="fas fa-magic me-1"></i>Timetable Active: <strong>${data.active_subject}</strong> (${data.day})`;
      }
    } else {
      if (timetableNotice) {
        timetableNotice.classList.add('d-none');
      }
    }
  } catch (err) {
    console.error("Failed to fetch timetable subject:", err);
  }

  // Auto-detect student count for distance range recommendation
  autoDetectStudentRange(classId);
}

// ─── Camera Source Switching (Local vs CCTV) ──────────────────────────────────
function switchCameraType(type) {
  currentCameraType = type;
  if (type === 'local') {
    localCamWrapper && localCamWrapper.classList.remove('d-none');
    cctvWrapper && cctvWrapper.classList.add('d-none');
    if (videoZoomWrapper) videoZoomWrapper.style.display = 'block';
    startLocalCamera(deviceSelect ? deviceSelect.value : null);
  } else {
    localCamWrapper && localCamWrapper.classList.add('d-none');
    cctvWrapper && cctvWrapper.classList.remove('d-none');
    stopLocalCamera();
  }
}

// ─── Enumerate Local Webcams ──────────────────────────────────────────────────
async function getDevices() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const videoDevices = devices.filter(d => d.kind === 'videoinput');
    if (deviceSelect) {
      deviceSelect.innerHTML = '';
      if (videoDevices.length === 0) {
        deviceSelect.innerHTML = '<option value="">Default Camera</option>';
      } else {
        videoDevices.forEach((device, index) => {
          const label = device.label || `Camera ${index + 1}`;
          deviceSelect.innerHTML += `<option value="${device.deviceId}">${label}</option>`;
        });
      }
    }
  } catch (err) {
    console.error('Error listing video devices:', err);
  }
}

// ─── Start / Stop Local Camera Stream ─────────────────────────────────────────
async function startLocalCamera(deviceId = null) {
  stopLocalCamera();
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showError('Webcam access is not supported by your browser.');
    return;
  }
  const constraints = {
    video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }
  };

  try {
    videoStream = await navigator.mediaDevices.getUserMedia(constraints);
    if (videoFeed) {
      videoFeed.srcObject = videoStream;
      videoFeed.style.display = 'block';
    }
    if (videoZoomWrapper) videoZoomWrapper.style.display = 'block';
    if (cameraPreviewBox) cameraPreviewBox.style.display = 'none';
    if (captureBtn) captureBtn.style.display = 'inline-block';
    if (retakeBtn) retakeBtn.style.display = 'none';
    currentZoom = 1.0;
    applyZoom();
  } catch (err) {
    console.error('Local camera start error:', err);
    showError('Could not access selected camera. Please check permissions or switch to CCTV / Upload mode.');
  }
}

function stopLocalCamera() {
  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
    videoStream = null;
  }
}

// ─── CCTV Stream Capture ──────────────────────────────────────────────────────
async function fetchCctvFrame() {
  const url = cctvUrlInput ? cctvUrlInput.value.trim() : '';
  if (!url) {
    showError('Please enter a valid RTSP/HTTP URL or camera index (e.g. 0).');
    return;
  }

  fetchCctvBtn.disabled = true;
  fetchCctvBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Fetching...';

  try {
    const res = await fetch('/capture-cctv', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });
    const data = await res.json();
    if (data.success && data.image) {
      selectedImageBase64 = data.image;
      if (cameraPreviewImg) cameraPreviewImg.src = selectedImageBase64;
      if (videoZoomWrapper) videoZoomWrapper.style.display = 'none';
      if (cameraPreviewBox) cameraPreviewBox.style.display = 'flex';
      if (captureBtn) captureBtn.style.display = 'none';
      if (retakeBtn) retakeBtn.style.display = 'inline-block';
      validateForm();
    } else {
      showError(data.error || 'Failed to capture frame from CCTV stream.');
    }
  } catch (err) {
    console.error('CCTV fetch error:', err);
    showError('Network error while connecting to CCTV proxy endpoint.');
  } finally {
    fetchCctvBtn.disabled = false;
    fetchCctvBtn.innerHTML = '<i class="fas fa-camera me-1"></i>Fetch CCTV Frame';
  }
}

// ─── Single Photo Capture from Local Stream ──────────────────────────────────
function captureSinglePhoto() {
  if (currentCameraType === 'cctv') {
    fetchCctvFrame();
    return;
  }

  if (!videoFeed || !videoFeed.videoWidth) {
    showError('Camera feed is not active yet.');
    return;
  }

  // Trigger flash animation
  if (cameraFlash) {
    cameraFlash.classList.add('flash-active');
    setTimeout(() => cameraFlash.classList.remove('flash-active'), 200);
  }

  captureCanvas.width = videoFeed.videoWidth;
  captureCanvas.height = videoFeed.videoHeight;
  const ctx = captureCanvas.getContext('2d');

  const scale = currentZoom;
  const w = captureCanvas.width;
  const h = captureCanvas.height;
  const sx = (w - w / scale) / 2;
  const sy = (h - h / scale) / 2;
  const sw = w / scale;
  const sh = h / scale;

  ctx.drawImage(videoFeed, sx, sy, sw, sh, 0, 0, w, h);
  selectedImageBase64 = captureCanvas.toDataURL('image/jpeg', 0.9);

  if (cameraPreviewImg) cameraPreviewImg.src = selectedImageBase64;
  if (videoZoomWrapper) videoZoomWrapper.style.display = 'none';
  if (cameraPreviewBox) cameraPreviewBox.style.display = 'flex';
  if (captureBtn) captureBtn.style.display = 'none';
  if (retakeBtn) retakeBtn.style.display = 'inline-block';
  validateForm();
}

function resetPhotoCapture() {
  selectedImageBase64 = null;
  if (cameraPreviewBox) cameraPreviewBox.style.display = 'none';
  if (videoZoomWrapper && currentCameraType === 'local') videoZoomWrapper.style.display = 'block';
  if (captureBtn) captureBtn.style.display = 'inline-block';
  if (retakeBtn) retakeBtn.style.display = 'none';
  if (resultSection) resultSection.classList.remove('show');
  validateForm();
}

// ─── Method Toggle (Live Camera vs Upload Photo) ──────────────────────────────
function switchMethod(mode) {
  currentMode = mode;
  btnCameraMode && btnCameraMode.classList.toggle('active', mode === 'camera');
  btnUploadMode && btnUploadMode.classList.toggle('active', mode === 'upload');
  cameraSection && cameraSection.classList.toggle('d-none', mode !== 'camera');
  uploadSection && uploadSection.classList.toggle('d-none', mode !== 'upload');

  if (mode === 'camera') {
    if (currentCameraType === 'local') startLocalCamera(deviceSelect ? deviceSelect.value : null);
  } else {
    stopLocalCamera();
  }
  validateForm();
}

// ─── Handle Uploaded File ─────────────────────────────────────────────────────
function handleSingleFile(file) {
  if (!file.type.startsWith('image/')) {
    showError('Please select a valid image file (JPG or PNG).');
    return;
  }

  const reader = new FileReader();
  reader.onload = (e) => {
    selectedImageBase64 = e.target.result;
    if (uploadPreviewImg) uploadPreviewImg.src = selectedImageBase64;
    if (dropZone) dropZone.style.display = 'none';
    if (uploadPreviewBox) uploadPreviewBox.style.display = 'flex';
    if (reselectContainer) reselectContainer.style.display = 'block';
    if (resultSection) resultSection.classList.remove('show');
    validateForm();
  };
  reader.readAsDataURL(file);
}

// ─── Zoom Controls ────────────────────────────────────────────────────────────
function setupZoomControls() {
  if (!zoomSlider) return;
  zoomSlider.addEventListener('input', (e) => {
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
  videoZoomWrapper && videoZoomWrapper.addEventListener('wheel', (e) => {
    e.preventDefault();
    const delta = e.deltaY * -0.001;
    currentZoom = Math.min(Math.max(MIN_ZOOM, currentZoom + delta), MAX_ZOOM);
    applyZoom();
  });
}

function applyZoom() {
  if (videoFeed) videoFeed.style.transform = `scale(${currentZoom})`;
  if (zoomSlider) zoomSlider.value = currentZoom;
  if (zoomLabel) zoomLabel.textContent = currentZoom.toFixed(1) + 'x';
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getClassId() {
  const el = document.getElementById('classSelect');
  if (!el) return '';
  if (typeof $ !== 'undefined' && $.fn.select2) {
    return $('#classSelect').val() || el.value || '';
  }
  return el.value || '';
}

function getSubjectName() {
  const inputEl = document.getElementById('subjectInput');
  if (inputEl && inputEl.value.trim()) return inputEl.value.trim();
  const selectEl = document.getElementById('subjectSelect');
  if (selectEl) {
    if (typeof $ !== 'undefined' && $.fn.select2) {
      return $('#subjectSelect').val() || selectEl.value || '';
    }
    return selectEl.value || '';
  }
  return '';
}

// ─── Form Validation ──────────────────────────────────────────────────────────
function validateForm() {
  // Keep button enabled so user clicks receive helpful feedback
  const btn = document.getElementById('submitBtn');
  if (btn) {
    btn.disabled = false;
  }
}

function showError(msg) {
  const errEl = document.getElementById('errorAlert') || errorAlert;
  if (errEl) {
    errEl.textContent = msg;
    errEl.classList.remove('d-none');
    errEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => errEl.classList.add('d-none'), 8000);
  } else {
    alert(msg);
  }
}

// ─── Convert Base64 DataURL to Blob File ──────────────────────────────────────
function dataURLtoBlob(dataurl) {
  const arr = dataurl.split(',');
  const mime = arr[0].match(/:(.*?);/)[1];
  const bstr = atob(arr[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);
  while (n--) {
    u8arr[n] = bstr.charCodeAt(n);
  }
  return new Blob([u8arr], { type: mime });
}

// ─── Submit Attendance ────────────────────────────────────────────────────────
async function submitAttendance(e) {
  if (e && e.preventDefault) e.preventDefault();
  
  const classId = getClassId();
  const subj = getSubjectName();

  if (!classId) {
    showError('Please select a class before marking attendance.');
    return;
  }

  // If photo hasn't been captured yet in camera mode, automatically capture frame
  if (!selectedImageBase64 && currentMode === 'camera') {
    if (currentCameraType === 'local' && videoFeed && videoFeed.videoWidth) {
      captureSinglePhoto();
    } else if (currentCameraType === 'cctv') {
      await fetchCctvFrame();
    }
  }

  if (!selectedImageBase64) {
    showError('Please capture or upload a classroom photo first.');
    return;
  }

  const errEl = document.getElementById('errorAlert') || errorAlert;
  if (errEl) errEl.classList.add('d-none');
  
  const resSec = document.getElementById('resultSection') || resultSection;
  if (resSec) resSec.classList.remove('show');
  
  const resContainer = document.getElementById('resultsContainer') || resultsContainer;
  if (resContainer) resContainer.innerHTML = '';
  
  const overlay = document.getElementById('loadingOverlay') || loadingOverlay;
  if (overlay) overlay.classList.add('d-flex');

  const csrfToken = document.getElementById('csrfToken')?.value || 
                    document.querySelector('input[name="csrf_token"]')?.value || '';

  const formData = new FormData();
  formData.append('class_id', classId);
  formData.append('subject_name', subj);
  formData.append('subject_id', subj);
  if (csrfToken) formData.append('csrf_token', csrfToken);
  formData.append('attendance_image', dataURLtoBlob(selectedImageBase64), 'attendance.jpg');
  formData.append('image_base64', selectedImageBase64);

  // Fixed 100m detection range for all attendance captures
  formData.append('detection_range', '100m');

  try {
    const headers = {};
    if (csrfToken) headers['X-CSRFToken'] = csrfToken;

    const res = await fetch(window.location.pathname, {
      method: 'POST',
      headers: headers,
      body: formData
    });

    let data;
    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      data = await res.json();
    } else {
      const text = await res.text();
      console.error('Non-JSON server response:', text);
      if (overlay) overlay.classList.remove('d-flex');
      showError(`Server error (${res.status}): ${res.statusText || 'Unexpected server response format.'}`);
      return;
    }

    if (overlay) overlay.classList.remove('d-flex');

    if (!res.ok || data.error) {
      showError(data.error || `Server error (${res.status}): Failed to process attendance.`);
    } else {
      renderResults(data);
      if (resSec) {
        resSec.classList.add('show');
        resSec.classList.remove('d-none');
        resSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  } catch (err) {
    console.error('Submit attendance error:', err);
    if (overlay) overlay.classList.remove('d-flex');
    showError('Connection error while sending request to server: ' + err.message);
  }
}

// Bind both vanilla and jQuery delegator for absolute certainty
if (typeof $ !== 'undefined') {
  $(document).on('click', '#submitBtn', submitAttendance);
}

// ─── Render Results Card (SCRFD + ArcFace Live Result UI) ─────────────────────
function renderResults(data) {
  let html = '';
  const recognized = data.recognized || data.recognized_students || [];
  const unknownCount = data.unknown_faces || 0;
  const rejectedCount = data.rejected_count || (data.rejected_faces ? data.rejected_faces.length : 0);
  const detectedCount = data.faces_detected || (recognized.length + unknownCount + rejectedCount);
  const markedCount = data.attendance_marked || recognized.length;
  const annotatedImage = data.annotated_image || null;
  const timings = data.timings || {};

  html += `
  <div class="card border-0 shadow-lg rounded-4 overflow-hidden mb-4" style="background: #ffffff; border: 1px solid rgba(0,0,0,0.08) !important;">
    <!-- Header with Stats Bar -->
    <div class="p-3 text-white d-flex justify-content-between align-items-center flex-wrap gap-2" style="background: linear-gradient(135deg, #2d3436, #0984e3);">
      <div>
        <h5 class="m-0 fw-bold"><i class="fas fa-camera me-2"></i>Classroom Attendance Result</h5>
        <small class="text-white-50"><i class="fas fa-microchip me-1"></i>SCRFD Face Detection + ArcFace Deep Embeddings</small>
      </div>
      <span class="badge bg-success rounded-pill px-3 py-2 fs-6 fw-bold">
        <i class="fas fa-check-circle me-1"></i>Attendance Marked: ${markedCount}
      </span>
    </div>

    <!-- Live Metric Cards Grid -->
    <div class="p-3 bg-light border-bottom">
      <div class="row g-2 text-center">
        <div class="col-6 col-md-3">
          <div class="p-2 rounded-3 bg-white shadow-sm border">
            <small class="text-muted text-uppercase fw-bold" style="font-size:0.75rem;">Detected</small>
            <div class="fs-4 fw-bold text-primary">${detectedCount}</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="p-2 rounded-3 bg-white shadow-sm border">
            <small class="text-muted text-uppercase fw-bold" style="font-size:0.75rem;">Recognized</small>
            <div class="fs-4 fw-bold text-success">${recognized.length}</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="p-2 rounded-3 bg-white shadow-sm border">
            <small class="text-muted text-uppercase fw-bold" style="font-size:0.75rem;">Unknown</small>
            <div class="fs-4 fw-bold text-warning">${unknownCount}</div>
          </div>
        </div>
        <div class="col-6 col-md-3">
          <div class="p-2 rounded-3 bg-white shadow-sm border">
            <small class="text-muted text-uppercase fw-bold" style="font-size:0.75rem;">Low Quality</small>
            <div class="fs-4 fw-bold text-secondary">${rejectedCount}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Annotated Image View (Color Bounding Boxes) -->
    ${annotatedImage ? `
    <div class="p-3 text-center bg-dark">
      <div class="d-flex justify-content-between align-items-center mb-2 px-1">
        <small class="text-white-50"><i class="fas fa-vector-square me-1"></i>Annotated Classroom Frame</small>
        <div class="d-flex gap-2">
          <span class="badge" style="background:#2ecc71;">● Recognized</span>
          <span class="badge" style="background:#f39c12;">● Unknown</span>
          <span class="badge" style="background:#e74c3c;">● Low Quality</span>
        </div>
      </div>
      <img src="${annotatedImage}" alt="Annotated Classroom Capture" class="img-fluid rounded-3 shadow" style="max-height: 480px; width: auto; object-fit: contain;">
    </div>
    ` : ''}

    <!-- Recognized Students List -->
    <div class="p-3">
      <h6 class="fw-bold mb-2 text-dark"><i class="fas fa-user-check text-success me-2"></i>Recognized Students</h6>
      ${recognized.length > 0 ? `
      <div class="list-group list-group-flush border rounded-3 overflow-hidden mb-3">
        ${recognized.map(student => {
          const conf = student.confidence ? `${student.confidence}%` : 'High';
          return `
          <div class="list-group-item d-flex justify-content-between align-items-center py-2 px-3">
            <div class="d-flex align-items-center gap-2">
              <span class="text-success fw-bold fs-5">✓</span>
              <div>
                <span class="fw-bold text-dark">${student.name}</span>
                <span class="text-muted small ms-2"><i class="fas fa-id-badge me-1"></i>${student.roll_number || ''}</span>
              </div>
            </div>
            <div class="d-flex align-items-center gap-2">
              <span class="badge rounded-pill text-white fw-bold px-2 py-1" style="background: linear-gradient(135deg, #00b894, #00cec9); font-size:0.78rem;">
                ${conf} match
              </span>
              <span class="badge bg-success bg-opacity-25 text-success rounded-pill px-2 py-1 small">
                ${student.status || 'Present'}
              </span>
            </div>
          </div>
          `;
        }).join('')}
      </div>
      ` : `
      <div class="alert alert-secondary py-2 px-3 small rounded-3 mb-3">
        No students identified from class registry.
      </div>
      `}

      <!-- Unknown Faces Section -->
      ${unknownCount > 0 ? `
      <h6 class="fw-bold mb-2 text-warning"><i class="fas fa-question-circle me-2"></i>Unrecognized Faces (${unknownCount})</h6>
      <div class="list-group list-group-flush border rounded-3 overflow-hidden mb-3">
        ${Array.from({length: unknownCount}).map((_, i) => `
        <div class="list-group-item d-flex justify-content-between align-items-center py-2 px-3 bg-light">
          <div class="d-flex align-items-center gap-2">
            <span class="text-warning fw-bold fs-5">?</span>
            <span class="text-muted fw-semibold">Unknown Person #${i + 1}</span>
          </div>
          <span class="badge bg-warning bg-opacity-25 text-dark rounded-pill px-2 py-1 small">-- Unregistered</span>
        </div>
        `).join('')}
      </div>
      ` : ''}

      <!-- Low Quality / Rejected Faces Breakdown -->
      ${rejectedCount > 0 && data.rejected_faces ? `
      <h6 class="fw-bold mb-2 text-secondary"><i class="fas fa-filter me-2"></i>Filtered / Low Quality Detections (${rejectedCount})</h6>
      <div class="list-group list-group-flush border rounded-3 overflow-hidden mb-3">
        ${data.rejected_faces.map((rf, i) => `
        <div class="list-group-item d-flex justify-content-between align-items-center py-2 px-3 small bg-light">
          <div class="text-muted">
            <span class="fw-semibold">Face Candidate #${i + 1}</span>
            <span class="ms-2 badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25">${rf.reason || 'Low Quality'}</span>
          </div>
          <span class="text-muted small">Excluded from attendance</span>
        </div>
        `).join('')}
      </div>
      ` : ''}

      <!-- Performance Timings Footer -->
      ${timings.total_sec ? `
      <div class="d-flex justify-content-between align-items-center text-muted small pt-2 border-top">
        <span><i class="fas fa-stopwatch me-1"></i>Total: <strong>${timings.total_sec}s</strong> (Det: ${timings.detection_sec || 0}s, Embed: ${timings.embedding_sec || 0}s, Search: ${timings.search_sec || 0}s)</span>
        <span>Range: <strong>${data.detection_range || 'Standard'}</strong></span>
      </div>
      ` : ''}
    </div>
  </div>
  `;

  if (resultsContainer) resultsContainer.innerHTML = html;
}

window.addEventListener('beforeunload', () => stopLocalCamera());
