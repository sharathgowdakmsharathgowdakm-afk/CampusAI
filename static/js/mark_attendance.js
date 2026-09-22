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
});

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

// ─── Render Results Card ──────────────────────────────────────────────────────
function renderResults(data) {
  let html = '';
  const recognized = data.recognized || data.recognized_students || [];
  const unknownCount = data.unknown_faces || 0;

  if (recognized.length > 0) {
    html += `
    <div class="card border-0 shadow-sm rounded-4 overflow-hidden mb-4" style="background: rgba(0, 184, 148, 0.08); border: 1px solid rgba(0, 184, 148, 0.3) !important;">
      <div class="p-3 text-white d-flex justify-content-between align-items-center" style="background: linear-gradient(135deg, #00b894, #00cec9);">
        <h5 class="m-0 fw-bold"><i class="fas fa-check-double me-2"></i>Successfully Marked Present</h5>
        <span class="badge bg-white text-success rounded-pill px-3 py-2 fw-bold">${recognized.length} Students</span>
      </div>
      <div class="list-group list-group-flush bg-transparent">
    `;

    recognized.forEach(student => {
      html += `
        <div class="list-group-item d-flex justify-content-between align-items-center bg-transparent py-3" style="border-color: rgba(0,0,0,0.05);">
          <div>
            <h6 class="m-0 fw-bold text-dark">${student.name}</h6>
            <small class="text-muted"><i class="fas fa-id-card me-1"></i>Roll: ${student.roll_number}</small>
          </div>
          <span class="badge bg-success bg-opacity-25 text-success rounded-pill px-3 py-2 fw-bold">
            <i class="fas fa-check me-1"></i>${student.status || 'Present'}
          </span>
        </div>
      `;
    });

    html += `</div></div>`;
  }

  if (unknownCount > 0) {
    html += `
    <div class="alert alert-warning rounded-4 d-flex align-items-center shadow-sm">
      <i class="fas fa-exclamation-triangle fa-2x me-3 text-warning"></i>
      <div>
        <h6 class="fw-bold mb-1">${unknownCount} Unrecognized Face(s) Detected</h6>
        <small>Faces were detected in the frame, but could not be matched with high confidence to registered students in this class.</small>
      </div>
    </div>
    `;
  }

  if (recognized.length === 0 && unknownCount === 0) {
    html = `
    <div class="alert alert-secondary rounded-4 text-center py-4 shadow-sm">
      <i class="fas fa-user-slash fa-3x text-muted mb-2"></i>
      <h5 class="fw-bold text-secondary">No Recognized Faces</h5>
      <p class="mb-0 text-muted">No student faces were recognized in the provided photo. Ensure lighting is clear and students are facing the camera.</p>
    </div>
    `;
  }

  if (resultsContainer) resultsContainer.innerHTML = html;
}

window.addEventListener('beforeunload', () => stopLocalCamera());
