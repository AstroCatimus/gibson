/**
 * Gibson — Scan Screen.
 * Barcode: EAN-13 978/979 only (ISBN). Rejects UPC-A, price supplements.
 * Photo: cover → title page → copyright page → send all 3 to Claude Vision.
 */

import { useState, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextInput,
  ActivityIndicator, Alert, Image, Modal, ScrollView,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { api } from '../../src/lib/api';

const GREEN  = '#2ecc71';
const YELLOW = '#f39c12';
const MUTED  = '#888';
const CARD   = '#13131f';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const YELLOW = '#f39c12';

const PHOTO_STEPS = [
  { key: 'cover',     label: 'Cover',          instruction: 'Point at the front cover and tap capture.' },
  { key: 'title',     label: 'Title page',      instruction: 'Open to the title page and tap capture.' },
  { key: 'copyright', label: 'Copyright page',  instruction: 'Flip to the copyright page (back of title page) and tap capture.' },
];

export default function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [mode, setMode]       = useState('barcode');
  const [loading, setLoading] = useState(false);
  const [manualIsbn, setManualIsbn] = useState('');

  // Multi-step photo state
  const [photoStep, setPhotoStep]     = useState(0);
  const [photos, setPhotos]           = useState([]);
  const [processing, setProcessing]   = useState(false);
  const [knownIsbn, setKnownIsbn]     = useState(null);

  // Multi-copy picker
  const [copyPickerResult, setCopyPickerResult] = useState(null); // full result when >1 copy

  const cameraRef      = useRef(null);
  const scanCooldown   = useRef(false);

  if (!permission) return <View style={s.container} />;

  if (!permission.granted) {
    return (
      <View style={[s.container, s.center]}>
        <Text style={s.permText}>Camera access needed to scan books.</Text>
        <TouchableOpacity style={s.btn} onPress={requestPermission}>
          <Text style={s.btnText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Barcode ──────────────────────────────────────────────────
  async function handleBarcode({ data, type }) {
    // Only accept EAN-13 barcodes that are ISBNs (978 / 979 prefix)
    if (type !== 'ean13') return;
    if (!data.startsWith('978') && !data.startsWith('979')) return;
    if (scanCooldown.current || loading) return;

    scanCooldown.current = true;
    setTimeout(() => { scanCooldown.current = false; }, 3000);
    setLoading(true);
    try {
      const result = await api.scanBarcode(data);
      if (result.title) {
        if (result.copies?.length > 1) {
          // Multiple physical copies — show picker first
          setCopyPickerResult(result);
        } else {
          router.push({ pathname: '/identify', params: { result: JSON.stringify(result) } });
        }
      } else {
        setKnownIsbn(data);
        setMode('photo');
        setPhotoStep(0);
        setPhotos([]);
      }
    } catch (e) {
      setMode('photo');
    } finally {
      setLoading(false);
    }
  }

  function handleCopyPick(copy) {
    // Inject the chosen copy's stock_item_id into the result before navigating
    const result = {
      ...copyPickerResult,
      stock_item_id: copy.stock_item_id,
      edition_id: copyPickerResult.edition_id,
      suggested_section: copy.section,
      condition_grade: copy.condition_grade,
      suggested_price: copy.asking_price ?? copyPickerResult.suggested_price,
      _picked_copy: copy,
    };
    setCopyPickerResult(null);
    router.push({ pathname: '/identify', params: { result: JSON.stringify(result) } });
  }

  // ── Multi-step photo ─────────────────────────────────────────
  function resetPhotoFlow() {
    setPhotoStep(0);
    setPhotos([]);
    setProcessing(false);
    setKnownIsbn(null);
  }

  async function capturePhoto() {
    if (!cameraRef.current || processing) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.8, base64: true });
      const next = [...photos, { uri: photo.uri, base64: photo.base64 }];
      setPhotos(next);

      if (next.length < PHOTO_STEPS.length) {
        // More steps remaining
        setPhotoStep(next.length);
      } else {
        // All 3 captured — send to API
        setProcessing(true);
        const [cover, title, copyright] = next;
        const result = await api.identifyPhoto(
          cover.base64,
          [title.base64, copyright.base64],
        );
        // If barcode gave us an ISBN but Claude couldn't read it, carry it forward
        if (knownIsbn && !result.isbn_13) result.isbn_13 = knownIsbn;
        router.push({
          pathname: '/identify',
          params: { result: JSON.stringify(result), coverUri: cover.uri },
        });
        resetPhotoFlow();
      }
    } catch (e) {
      Alert.alert('Error', e.message);
      setProcessing(false);
    }
  }

  // ── Manual ISBN ──────────────────────────────────────────────
  async function handleManualIsbn() {
    const isbn = manualIsbn.replace(/[^0-9X]/gi, '');
    if (isbn.length !== 13 && isbn.length !== 10) {
      Alert.alert('Invalid ISBN', 'ISBN must be 10 or 13 digits.');
      return;
    }
    setLoading(true);
    try {
      const result = await api.scanBarcode(isbn);
      router.push({ pathname: '/identify', params: { result: JSON.stringify(result) } });
    } catch (e) {
      Alert.alert('Not found', e.message);
    } finally {
      setLoading(false);
    }
  }

  const currentStep = PHOTO_STEPS[photoStep];
  const thumbUri    = photos[0]?.uri;  // cover thumbnail

  return (
    <View style={s.container}>
      <CameraView
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
        facing="back"
        onBarcodeScanned={mode === 'barcode' ? handleBarcode : undefined}
        barcodeScannerSettings={{ barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e'] }}
      />

      {/* Mode selector */}
      <View style={s.modeBar}>
        {['barcode', 'photo', 'manual'].map((m) => (
          <TouchableOpacity
            key={m}
            style={[s.modeBtn, mode === m && s.modeBtnActive]}
            onPress={() => { setMode(m); resetPhotoFlow(); }}
          >
            <Text style={[s.modeBtnText, mode === m && s.modeBtnTextActive]}>
              {m === 'barcode' ? 'Barcode' : m === 'photo' ? 'Cover' : 'Manual'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Barcode frame */}
      {mode === 'barcode' && (
        <View style={s.crosshair} pointerEvents="none">
          <View style={s.crosshairBox} />
          <Text style={s.crosshairLabel}>ISBN barcode only (978 / 979)</Text>
        </View>
      )}

      {/* Loading / processing overlay */}
      {(loading || processing) && (
        <View style={s.loadingOverlay} pointerEvents="none">
          <ActivityIndicator color={ACCENT} size="large" />
          {processing && (
            <Text style={s.processingLabel}>Identifying with Claude Vision…</Text>
          )}
        </View>
      )}

      {/* Bottom controls */}
      <View style={s.controls}>

        {/* ── Photo multi-step ── */}
        {mode === 'photo' && !processing && (
          <>
            {/* Barcode miss banner */}
            {knownIsbn && (
              <View style={s.isbnBanner}>
                <Text style={s.isbnBannerText}>
                  ISBN {knownIsbn} not in database — identify from photos
                </Text>
              </View>
            )}

            {/* Step indicators */}
            <View style={s.stepRow}>
              {PHOTO_STEPS.map((step, i) => (
                <View key={step.key} style={s.stepItem}>
                  <View style={[
                    s.stepDot,
                    i < photos.length && s.stepDotDone,
                    i === photoStep && s.stepDotActive,
                  ]}>
                    {i < photos.length
                      ? <Text style={s.stepDotCheck}>✓</Text>
                      : <Text style={[s.stepDotNum, i === photoStep && { color: '#fff' }]}>{i + 1}</Text>
                    }
                  </View>
                  <Text style={[s.stepLabel, i === photoStep && s.stepLabelActive]}>
                    {step.label}
                  </Text>
                </View>
              ))}
            </View>

            {/* Cover thumbnail + instructions */}
            <View style={s.photoRow}>
              {thumbUri ? (
                <Image source={{ uri: thumbUri }} style={s.thumb} />
              ) : null}
              <Text style={[s.instruction, thumbUri && { flex: 1 }]}>
                {currentStep.instruction}
              </Text>
            </View>

            <TouchableOpacity style={s.captureBtn} onPress={capturePhoto}>
              <Text style={s.captureBtnText}>
                {photoStep === 0 ? 'Take Cover Photo'
                  : photoStep === 1 ? 'Take Title Page'
                  : 'Take Copyright Page'}
              </Text>
            </TouchableOpacity>

            {photoStep > 0 && (
              <TouchableOpacity style={s.skipBtn} onPress={async () => {
                // Allow skipping remaining steps — send what we have
                setProcessing(true);
                try {
                  const [cover, ...rest] = photos;
                  const result = await api.identifyPhoto(cover.base64, rest.map(p => p.base64));
                  router.push({
                    pathname: '/identify',
                    params: { result: JSON.stringify(result), coverUri: cover.uri },
                  });
                  resetPhotoFlow();
                } catch (e) {
                  Alert.alert('Error', e.message);
                  setProcessing(false);
                }
              }}>
                <Text style={s.skipBtnText}>Skip remaining pages →</Text>
              </TouchableOpacity>
            )}
          </>
        )}

        {/* ── Manual ISBN ── */}
        {mode === 'manual' && (
          <View style={s.manualRow}>
            <TextInput
              style={s.isbnInput}
              value={manualIsbn}
              onChangeText={setManualIsbn}
              placeholder="ISBN (10 or 13 digits)"
              placeholderTextColor="#555"
              keyboardType="numeric"
              maxLength={17}
            />
            <TouchableOpacity
              style={[s.lookupBtn, loading && s.btnDisabled]}
              onPress={handleManualIsbn}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color="#fff" size="small" />
                : <Text style={s.btnText}>Look Up</Text>
              }
            </TouchableOpacity>
          </View>
        )}

        {mode === 'barcode' && (
          <Text style={s.hint}>Scanning automatically…</Text>
        )}

      </View>

      {/* ── Multi-copy picker modal ───────────────────────── */}
      <Modal
        visible={!!copyPickerResult}
        transparent
        animationType="slide"
        onRequestClose={() => setCopyPickerResult(null)}
      >
        <View style={cp.overlay}>
          <View style={cp.sheet}>
            <Text style={cp.title}>{copyPickerResult?.title}</Text>
            <Text style={cp.sub}>
              {copyPickerResult?.copies?.length} copies in stock — which one are you holding?
            </Text>
            <ScrollView style={{ maxHeight: 360 }}>
              {(copyPickerResult?.copies || []).map((copy) => (
                <TouchableOpacity
                  key={copy.stock_item_id}
                  style={cp.copyRow}
                  onPress={() => handleCopyPick(copy)}
                >
                  <View style={cp.copyLeft}>
                    <Text style={cp.skuText}>{copy.gibson_sku}</Text>
                    <Text style={cp.sectionText}>{copy.section || 'No section'}</Text>
                  </View>
                  <View style={cp.copyRight}>
                    <Text style={cp.condText}>{copy.condition_grade || '—'}</Text>
                    <Text style={cp.priceText}>
                      {copy.asking_price ? `$${Number(copy.asking_price).toFixed(2)}` : 'No price'}
                    </Text>
                  </View>
                  <Text style={cp.arrow}>›</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <TouchableOpacity style={cp.cancelBtn} onPress={() => setCopyPickerResult(null)}>
              <Text style={cp.cancelTxt}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

    </View>
  );
}

const cp = StyleSheet.create({
  overlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: CARD, borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: 24, paddingBottom: 40,
  },
  title:   { color: '#fff', fontSize: 17, fontWeight: '700', marginBottom: 4 },
  sub:     { color: MUTED, fontSize: 13, marginBottom: 16 },
  copyRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#1e1e2e', borderRadius: 12,
    padding: 14, marginBottom: 10,
  },
  copyLeft:    { flex: 1 },
  copyRight:   { alignItems: 'flex-end', marginRight: 12 },
  skuText:     { color: '#fff', fontWeight: '700', fontSize: 14 },
  sectionText: { color: MUTED, fontSize: 12, marginTop: 2 },
  condText:    { color: GREEN, fontSize: 13, fontWeight: '600' },
  priceText:   { color: YELLOW, fontSize: 13, marginTop: 2 },
  arrow:       { color: MUTED, fontSize: 20 },
  cancelBtn:   { marginTop: 8, alignItems: 'center', padding: 12 },
  cancelTxt:   { color: MUTED, fontSize: 15 },
});

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  center: { alignItems: 'center', justifyContent: 'center' },
  permText: { color: '#fff', textAlign: 'center', margin: 20, fontSize: 15 },

  modeBar: {
    position: 'absolute', top: 56, left: 0, right: 0,
    flexDirection: 'row', justifyContent: 'center', gap: 8, paddingHorizontal: 16,
  },
  modeBtn: {
    paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.25)',
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modeBtnActive: { backgroundColor: ACCENT, borderColor: ACCENT },
  modeBtnText: { color: 'rgba(255,255,255,0.65)', fontSize: 13 },
  modeBtnTextActive: { color: '#fff', fontWeight: '600' },

  crosshair: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 100,
    alignItems: 'center', justifyContent: 'center',
  },
  crosshairBox: { width: 260, height: 110, borderWidth: 2, borderColor: ACCENT, borderRadius: 8 },
  crosshairLabel: { color: '#fff', marginTop: 10, opacity: 0.75, fontSize: 12 },

  loadingOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.55)', alignItems: 'center', justifyContent: 'center', gap: 12,
  },
  processingLabel: { color: '#fff', fontSize: 14, opacity: 0.9 },

  controls: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(13,13,25,0.95)', padding: 16, paddingBottom: 36,
    gap: 12,
  },

  // Step indicators
  stepRow: { flexDirection: 'row', justifyContent: 'center', gap: 24, marginBottom: 4 },
  stepItem: { alignItems: 'center', gap: 4 },
  stepDot: {
    width: 28, height: 28, borderRadius: 14,
    borderWidth: 1, borderColor: '#333',
    backgroundColor: '#1a1a2a', alignItems: 'center', justifyContent: 'center',
  },
  stepDotActive: { borderColor: ACCENT, backgroundColor: '#2a0d1a' },
  stepDotDone: { borderColor: '#2ecc71', backgroundColor: '#0d2a15' },
  stepDotNum: { color: '#555', fontSize: 12, fontWeight: '700' },
  stepDotCheck: { color: '#2ecc71', fontSize: 12, fontWeight: '700' },
  stepLabel: { color: '#555', fontSize: 10 },
  stepLabelActive: { color: '#fff' },

  // Photo controls
  photoRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  thumb: { width: 44, height: 60, borderRadius: 4, borderWidth: 1, borderColor: '#333' },
  instruction: { color: '#aaa', fontSize: 13, lineHeight: 18, textAlign: 'center' },

  captureBtn: { backgroundColor: ACCENT, padding: 15, borderRadius: 12, alignItems: 'center' },
  captureBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },

  skipBtn: { alignItems: 'center', paddingVertical: 4 },
  skipBtnText: { color: '#555', fontSize: 13 },

  // Manual
  manualRow: { flexDirection: 'row', gap: 10 },
  isbnInput: {
    flex: 1, backgroundColor: '#1e1e2e', borderWidth: 1, borderColor: '#333',
    borderRadius: 10, padding: 12, color: '#fff', fontSize: 15,
  },
  lookupBtn: { backgroundColor: ACCENT, padding: 12, borderRadius: 10, justifyContent: 'center' },
  btn: { backgroundColor: ACCENT, padding: 14, borderRadius: 10, alignItems: 'center', marginTop: 12 },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#fff', fontWeight: '600' },
  hint: { color: 'rgba(255,255,255,0.45)', textAlign: 'center', fontSize: 13 },

  isbnBanner: {
    backgroundColor: '#1a1a10', borderWidth: 1, borderColor: '#3a3a10',
    borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7,
  },
  isbnBannerText: { color: '#aaa', fontSize: 12, textAlign: 'center' },
});
