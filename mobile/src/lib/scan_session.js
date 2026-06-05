/**
 * Scan session store.
 * Holds the raw base64 photos from the current scan so deep_lookup.js
 * can access them without passing multi-MB strings through navigation params.
 * Cleared when a new scan starts.
 */

let _session = {
  cover:     null,  // base64
  title:     null,  // base64
  copyright: null,  // base64
};

export function storeScanPhotos(cover, title, copyright) {
  _session = { cover: cover || null, title: title || null, copyright: copyright || null };
}

export function getScanPhotos() {
  return { ..._session };
}

export function clearScanPhotos() {
  _session = { cover: null, title: null, copyright: null };
}

/** Returns non-null images as an array: [cover, title, copyright] */
export function getScanPhotoArray() {
  return [_session.cover, _session.title, _session.copyright].filter(Boolean);
}
