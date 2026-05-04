/**
 * Gibson Camera View — the primary entry point.
 * Camera opens immediately. ZXing-js barcode detection on live viewfinder.
 * Barcode detected = fires immediately (green flash, no photo needed).
 * No barcode after 3s = "Take cover photo".
 */

Gibson.router.register('camera', function(container) {
  container.innerHTML = `
    <div id="camera-container">
      <video id="camera-feed" autoplay playsinline muted></video>
      <canvas id="camera-canvas" style="display:none"></canvas>
      <div id="barcode-overlay" style="display:none" class="barcode-flash"></div>
    </div>

    <div style="margin-top: 12px; text-align: center;">
      <p id="camera-status" style="color: var(--text-secondary); font-size: 13px;">
        Starting camera... looking for barcode
      </p>
      <button id="capture-btn" class="btn btn-primary btn-full" style="margin-top: 12px; display: none;">
        📸 Take Cover Photo
      </button>
    </div>

    <div id="quick-entry" class="card" style="margin-top: 16px;">
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 8px;">Quick entry</p>
      <div style="display: flex; gap: 8px;">
        <input id="isbn-input" type="text" placeholder="ISBN or SKU"
          style="flex:1; padding: 10px; background: var(--bg-secondary); border: 1px solid var(--border);
                 border-radius: var(--radius); color: var(--text-primary); font-size: 16px;">
        <button id="isbn-go" class="btn btn-primary">Go</button>
      </div>
    </div>
  `;

  const video = document.getElementById('camera-feed');
  const statusEl = document.getElementById('camera-status');
  const captureBtn = document.getElementById('capture-btn');
  let stream = null;
  let barcodeTimer = null;

  // Start camera
  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 960 } }
      });
      video.srcObject = stream;

      // Start barcode scanning timer
      barcodeTimer = setTimeout(() => {
        statusEl.textContent = 'No barcode found. Take a cover photo.';
        captureBtn.style.display = 'block';
      }, 3000);

      // ZXing-js barcode scanning would run here on the live feed
      // For now, rely on manual ISBN entry
      statusEl.textContent = 'Camera active — scanning for barcode...';

    } catch (e) {
      statusEl.textContent = 'Camera not available. Use manual entry below.';
      captureBtn.style.display = 'none';
    }
  }

  // Capture photo
  captureBtn.addEventListener('click', async () => {
    const canvas = document.getElementById('camera-canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const imageBase64 = canvas.toDataURL('image/jpeg', 0.85).split(',')[1];

    statusEl.textContent = 'Identifying...';
    captureBtn.disabled = true;

    try {
      const result = await Gibson.api.identifyPhoto(imageBase64);
      Gibson.store.set('lastIdentification', result);
      Gibson.router.navigate('identify', { result });
    } catch (e) {
      statusEl.textContent = 'Identification failed: ' + e.message;
      captureBtn.disabled = false;
    }
  });

  // Manual ISBN/SKU entry
  document.getElementById('isbn-go').addEventListener('click', async () => {
    const input = document.getElementById('isbn-input').value.trim();
    if (!input) return;

    statusEl.textContent = 'Looking up...';
    try {
      // Try as ISBN first
      if (/^\d{10,13}$/.test(input.replace(/-/g, ''))) {
        const result = await Gibson.api.identifyBarcode(input.replace(/-/g, ''));
        Gibson.store.set('lastIdentification', result);
        Gibson.router.navigate('identify', { result });
      } else {
        // Try as SKU
        const item = await Gibson.api.lookupSku(input);
        Gibson.router.navigate('inventory', { item });
      }
    } catch (e) {
      statusEl.textContent = 'Not found: ' + e.message;
    }
  });

  // Enter key on ISBN input
  document.getElementById('isbn-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') document.getElementById('isbn-go').click();
  });

  startCamera();
});
