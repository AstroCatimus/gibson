/**
 * Gibson Shelfie / Shelf Scan view.
 * Wide angle shelf photo → spine detection → color overlay.
 * GREEN=matched, YELLOW=location conflict, RED=not in db, GREY=OCR fail
 */

Gibson.router.register('shelfie', function(container) {
  container.innerHTML = `
    <div class="card">
      <h3 style="margin-bottom: 8px;">Shelf Scan</h3>
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
        Photograph a shelf to identify visible spines
      </p>
      <div id="shelf-camera" style="width:100%; aspect-ratio: 16/9; background: #000; border-radius: var(--radius); margin-bottom: 12px;">
        <video id="shelf-feed" autoplay playsinline muted style="width:100%;height:100%;object-fit:cover;border-radius:var(--radius);"></video>
      </div>
      <button id="shelf-capture" class="btn btn-primary btn-full">📸 Scan Shelf</button>
    </div>
    <div id="shelf-results"></div>
  `;

  // Start camera in landscape-ish mode
  navigator.mediaDevices.getUserMedia({
    video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }
  }).then(stream => {
    document.getElementById('shelf-feed').srcObject = stream;
  }).catch(() => {});

  document.getElementById('shelf-capture').addEventListener('click', () => {
    document.getElementById('shelf-results').innerHTML = `
      <div class="card">
        <div class="spinner" style="margin: 20px auto;"></div>
        <p style="text-align:center;color:var(--text-muted);margin-top:8px;">Processing spines...</p>
      </div>
    `;
    // In production: capture frame, send to /api/shelfie/scan, render overlay
    setTimeout(() => {
      document.getElementById('shelf-results').innerHTML = `
        <div class="card">
          <p style="text-align:center;color:var(--text-muted);padding:20px;">
            Shelf scan requires YOLOv8n model (Phase 9).<br>
            Pipeline ready — model not yet loaded.
          </p>
        </div>
      `;
    }, 1500);
  });
});
