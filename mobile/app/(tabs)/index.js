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
import { storeScanPhotos, clearScanPhotos } from '../../src/lib/scan_session';
import { C } from '../../src/lib/theme';

const PHOTO_STEPS = [
  { key: 'cover',     label: 'Cover',         instruction: 'Point at the front cover and tap capture.' },
  { key: 'title',     label: 'Title page',     instruction: 'Open to the title page and tap capture.' },
  { key: 'copyright', label: 'Copyright page', instruction: 'Flip to the copyright page (back of title page) and tap capture.' },
];

export default function ScanScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [mode, setMode]       = useState('barcode');
  const [loading, setLoading] = useState(false);
  const [manualIsbn, setManualIsbn] = useState('');
  const [torch, setTorch]     = useState(false);

  const [photoStep, setPhotoStep]   = useState(0);
  const [photos, setPhotos]         = useState([]);
  const [processing, setProcessing] = useState(false);
  const [knownIsbn, setKnownIsbn]   = useState(null);

  const [copyPickerResult, setCopyPickerResult] = useState(null);

  const cameraRef    = useRef(null);
  const scanCooldown = useRef(false);

  if (!permission) return <View style={s.container} />;

  if (!permission.granted) {
    return (
      <View style={[s.container, s.center]}>
        <Text style={s.permIcon}>📷</Text>
        <Text style={s.permText}>Camera access is needed to scan books.</Text>
        <TouchableOpacity style={s.permBtn} onPress={requestPermission}>
          <Text style={s.permBtnText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Barcode ─────────────────────────────────────────────────────
  async function handleBarcode({ data, type }) {
    if (type !== 'ean13') return;
    if (!data.startsWith('978') && !data.startsWith('979')) return;
    if (scanCooldown.current || loading) return;

    scanCooldown.current = true;
    setTimeout(() => { scanCooldown.current = false; }, 3000);
    setLoading(true);
    try {
      const result = await api.scanBarcode(data);
      if (result.title) {
        // Delay torch off slightly so the scan confirmation feels responsive
        setTimeout(() => setTorch(false), 500);
        if (result.copies?.length > 1) {
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

  // ── Multi-step photo ─────────────────────────────────────────────
  function resetPhotoFlow() {
    setPhotoStep(0);
    setPhotos([]);
    setProcessing(false);
    setKnownIsbn(null);
    clearScanPhotos();
  }

  async function capturePhoto() {
    if (!cameraRef.current || processing) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.8, base64: true });
      const next = [...photos, { uri: photo.uri, base64: photo.base64 }];
      setPhotos(next);

      if (next.length < PHOTO_STEPS.length) {
        setPhotoStep(next.length);
      } else {
        setProcessing(true);
        const [cover, title, copyright] = next;
        // Store photos for deep lookup before navigating away
        storeScanPhotos(cover.base64, title.base64, copyright.base64);
        const result = await api.identifyPhoto(cover.base64, [title.base64, copyright.base64]);
        if (knownIsbn && !result.isbn_13) result.isbn_13 = knownIsbn;
        setTimeout(() => setTorch(false), 500);
        router.push({ pathname: '/identify', params: { result: JSON.stringify(result), coverUri: cover.uri } });
        resetPhotoFlow();
      }
    } catch (e) {
      Alert.alert('Error', e.message);
      setProcessing(false);
    }
  }

  // ── Manual ISBN ──────────────────────────────────────────────────
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
  const thumbUri    = photos[0]?.uri;

  return (
    <View style={s.container}>
      <CameraView
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
        facing="back"
        enableTorch={torch}
        onBarcodeScanned={mode === 'barcode' ? handleBarcode : undefined}
        barcodeScannerSettings={{ barcodeTypes: ['ean13', 'ean8', 'upc_a', 'upc_e'] }}
      />

      {/* ── Mode bar ── */}
      <View style={s.modeBar}>
        {[
          { key: 'barcode', label: 'Barcode' },
          { key: 'photo',   label: 'Cover' },
          { key: 'manual',  label: 'Manual' },
        ].map(({ key, label }) => (
          <TouchableOpacity
            key={key}
            style={[s.modeBtn, mode === key && s.modeBtnActive]}
            onPress={() => { setMode(key); resetPhotoFlow(); }}
          >
            <Text style={[s.modeBtnText, mode === key && s.modeBtnTextActive]}>
              {label}
            </Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity
          style={[s.torchBtn, torch && s.torchBtnActive]}
          onPress={() => setTorch(t => !t)}
        >
          <Text style={s.torchIcon}>⚡</Text>
        </TouchableOpacity>
      </View>

      {/* ── Barcode crosshair ── */}
      {mode === 'barcode' && (
        <View style={s.crosshair} pointerEvents="none">
          <View style={s.crosshairCorners}>
            <View style={s.crosshairBox} />
          </View>
          <Text style={s.crosshairLabel}>ISBN barcode (978 · 979)</Text>
        </View>
      )}

      {/* ── Photo alignment guide ── */}
      {mode === 'photo' && !processing && (
        <View style={s.photoGuideWrap} pointerEvents="none">
          <View style={s.photoGuideFrame}>
            {/* Four corner markers — subtle L-shapes */}
            <View style={[s.corner, s.cornerTL]} />
            <View style={[s.corner, s.cornerTR]} />
            <View style={[s.corner, s.cornerBL]} />
            <View style={[s.corner, s.cornerBR]} />
            {/* Centre step label */}
            <Text style={s.guideLabelText}>
              {photoStep === 0 ? 'book cover'
                : photoStep === 1 ? 'title page'
                : 'copyright page'}
            </Text>
          </View>
        </View>
      )}

      {/* ── Loading overlay ── */}
      {(loading || processing) && (
        <View style={s.loadingOverlay} pointerEvents="none">
          <ActivityIndicator color={C.accent} size="large" />
          {processing && (
            <Text style={s.processingLabel}>Identifying with Claude Vision…</Text>
          )}
        </View>
      )}

      {/* ── Bottom controls ── */}
      <View style={s.controls}>

        {mode === 'photo' && !processing && (
          <>
            {knownIsbn && (
              <View style={s.isbnBanner}>
                <Text style={s.isbnBannerText}>
                  ISBN {knownIsbn} not in database — identify from photos
                </Text>
              </View>
            )}

            {/* Step progress */}
            <View style={s.stepRow}>
              {PHOTO_STEPS.map((step, i) => (
                <View key={step.key} style={s.stepItem}>
                  <View style={[
                    s.stepDot,
                    i < photos.length && s.stepDotDone,
                    i === photoStep && s.stepDotActive,
                  ]}>
                    {i < photos.length
                      ? <Text style={s.stepCheck}>✓</Text>
                      : <Text style={[s.stepNum, i === photoStep && { color: C.text }]}>{i + 1}</Text>
                    }
                  </View>
                  <Text style={[s.stepLabel, i === photoStep && s.stepLabelActive]}>
                    {step.label}
                  </Text>
                </View>
              ))}
            </View>

            {/* Instruction row */}
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
                {photoStep === 0 ? '📷  Take Cover Photo'
                  : photoStep === 1 ? '📷  Take Title Page'
                  : '📷  Take Copyright Page'}
              </Text>
            </TouchableOpacity>

            {photoStep > 0 && (
              <TouchableOpacity style={s.skipBtn} onPress={async () => {
                setProcessing(true);
                try {
                  const [cover, ...rest] = photos;
                  const result = await api.identifyPhoto(cover.base64, rest.map(p => p.base64));
                  setTimeout(() => setTorch(false), 500);
                  router.push({ pathname: '/identify', params: { result: JSON.stringify(result), coverUri: cover.uri } });
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

        {mode === 'manual' && (
          <View style={s.manualRow}>
            <TextInput
              style={s.isbnInput}
              value={manualIsbn}
              onChangeText={setManualIsbn}
              placeholder="ISBN — 10 or 13 digits"
              placeholderTextColor={C.text3}
              keyboardType="numeric"
              maxLength={17}
            />
            <TouchableOpacity
              style={[s.lookupBtn, loading && s.btnDisabled]}
              onPress={handleManualIsbn}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color={C.bg} size="small" />
                : <Text style={s.lookupBtnText}>Look Up</Text>
              }
            </TouchableOpacity>
          </View>
        )}

        {mode === 'barcode' && (
          <Text style={s.hint}>Scanning automatically…</Text>
        )}
      </View>

      {/* ── Multi-copy picker ── */}
      <Modal
        visible={!!copyPickerResult}
        transparent
        animationType="slide"
        onRequestClose={() => setCopyPickerResult(null)}
      >
        <View style={cp.overlay}>
          <View style={cp.sheet}>
            <View style={cp.handle} />
            <Text style={cp.title}>{copyPickerResult?.title}</Text>
            <Text style={cp.sub}>
              {copyPickerResult?.copies?.length} copies in stock — which one are you holding?
            </Text>
            <ScrollView style={{ maxHeight: 360 }} showsVerticalScrollIndicator={false}>
              {(copyPickerResult?.copies || []).map((copy) => (
                <TouchableOpacity
                  key={copy.stock_item_id}
                  style={cp.copyRow}
                  onPress={() => handleCopyPick(copy)}
                  activeOpacity={0.75}
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
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: C.card, borderTopLeftRadius: 24, borderTopRightRadius: 24,
    padding: 24, paddingBottom: 40, borderTopWidth: 1, borderColor: C.border,
  },
  handle: {
    width: 36, height: 4, borderRadius: 2,
    backgroundColor: C.border, alignSelf: 'center', marginBottom: 20,
  },
  title:  { color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 4 },
  sub:    { color: C.text2, fontSize: 13, marginBottom: 16 },
  copyRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.surface, borderRadius: 12,
    padding: 14, marginBottom: 8,
    borderWidth: 1, borderColor: C.border,
  },
  copyLeft:    { flex: 1 },
  copyRight:   { alignItems: 'flex-end', marginRight: 12 },
  skuText:     { color: C.text, fontWeight: '700', fontSize: 14, fontFamily: 'monospace' },
  sectionText: { color: C.text2, fontSize: 12, marginTop: 2 },
  condText:    { color: C.green, fontSize: 13, fontWeight: '600' },
  priceText:   { color: C.accent, fontSize: 13, fontWeight: '700', marginTop: 2 },
  arrow:       { color: C.text3, fontSize: 20 },
  cancelBtn:   { marginTop: 10, alignItems: 'center', padding: 12 },
  cancelTxt:   { color: C.text2, fontSize: 15 },
});

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  center:    { alignItems: 'center', justifyContent: 'center', padding: 32 },
  permIcon:  { fontSize: 48, marginBottom: 16 },
  permText:  { color: C.text2, textAlign: 'center', fontSize: 15, lineHeight: 22, marginBottom: 24 },
  permBtn:   { backgroundColor: C.accent, paddingVertical: 14, paddingHorizontal: 32, borderRadius: 12 },
  permBtnText: { color: C.bg, fontWeight: '700', fontSize: 15 },

  // Mode selector
  modeBar: {
    position: 'absolute', top: 56, left: 0, right: 0,
    flexDirection: 'row', justifyContent: 'center', gap: 8, paddingHorizontal: 20,
  },
  modeBtn: {
    paddingHorizontal: 18, paddingVertical: 9, borderRadius: 20,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)',
    backgroundColor: 'rgba(19,17,14,0.75)',
  },
  modeBtnActive: { backgroundColor: C.accent, borderColor: C.accent },
  modeBtnText: { color: 'rgba(255,255,255,0.6)', fontSize: 13, fontWeight: '500' },
  modeBtnTextActive: { color: C.bg, fontWeight: '700' },
  torchBtn: {
    paddingHorizontal: 14, paddingVertical: 9, borderRadius: 20,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)',
    backgroundColor: 'rgba(19,17,14,0.75)',
  },
  torchBtnActive: { backgroundColor: C.yellow, borderColor: C.yellow },
  torchIcon: { fontSize: 15 },

  // Barcode crosshair
  crosshair: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 100,
    alignItems: 'center', justifyContent: 'center',
  },
  crosshairCorners: { position: 'relative' },
  crosshairBox: {
    width: 270, height: 115,
    borderWidth: 2, borderColor: C.accent,
    borderRadius: 10, opacity: 0.9,
  },
  crosshairLabel: { color: 'rgba(255,255,255,0.7)', marginTop: 12, fontSize: 12, letterSpacing: 0.3 },

  // Photo alignment guide
  photoGuideWrap: {
    position: 'absolute', top: 96, left: 0, right: 0, bottom: 210,
    alignItems: 'center', justifyContent: 'center',
  },
  photoGuideFrame: {
    width: 230, height: 320,
    alignItems: 'center', justifyContent: 'center',
  },
  // L-shaped corner markers — 2px lines, 28px long, amber at 60% opacity
  corner: {
    position: 'absolute',
    width: 28, height: 28,
    borderColor: 'rgba(200,144,46,0.65)',
    borderWidth: 2,
  },
  cornerTL: { top: 0, left: 0, borderRightWidth: 0, borderBottomWidth: 0, borderTopLeftRadius: 3 },
  cornerTR: { top: 0, right: 0, borderLeftWidth: 0, borderBottomWidth: 0, borderTopRightRadius: 3 },
  cornerBL: { bottom: 0, left: 0, borderRightWidth: 0, borderTopWidth: 0, borderBottomLeftRadius: 3 },
  cornerBR: { bottom: 0, right: 0, borderLeftWidth: 0, borderTopWidth: 0, borderBottomRightRadius: 3 },
  guideLabelText: {
    color: 'rgba(255,255,255,0.38)',
    fontSize: 11, letterSpacing: 0.8,
    textTransform: 'uppercase',
  },

  // Loading overlay
  loadingOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(19,17,14,0.65)', alignItems: 'center', justifyContent: 'center', gap: 14,
  },
  processingLabel: { color: C.text, fontSize: 14, opacity: 0.9, letterSpacing: 0.2 },

  // Bottom controls panel
  controls: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(19,17,14,0.96)',
    borderTopWidth: 1, borderTopColor: C.border,
    padding: 16, paddingBottom: 36, gap: 12,
  },

  // Step indicators
  stepRow: { flexDirection: 'row', justifyContent: 'center', gap: 28, marginBottom: 2 },
  stepItem: { alignItems: 'center', gap: 5 },
  stepDot: {
    width: 30, height: 30, borderRadius: 15,
    borderWidth: 1.5, borderColor: C.text3,
    backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center',
  },
  stepDotActive: { borderColor: C.accent, backgroundColor: C.accentBg },
  stepDotDone:   { borderColor: C.green,  backgroundColor: C.greenBg },
  stepNum:   { color: C.text3, fontSize: 12, fontWeight: '700' },
  stepCheck: { color: C.green, fontSize: 12, fontWeight: '700' },
  stepLabel: { color: C.text3, fontSize: 10, letterSpacing: 0.2 },
  stepLabelActive: { color: C.text },

  // Photo controls
  photoRow:    { flexDirection: 'row', alignItems: 'center', gap: 12 },
  thumb:       { width: 44, height: 60, borderRadius: 6, borderWidth: 1, borderColor: C.border },
  instruction: { color: C.text2, fontSize: 13, lineHeight: 19, textAlign: 'center' },

  captureBtn: {
    backgroundColor: C.accent, padding: 15, borderRadius: 12,
    alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
  },
  captureBtnText: { color: C.bg, fontSize: 15, fontWeight: '700' },

  skipBtn:     { alignItems: 'center', paddingVertical: 4 },
  skipBtnText: { color: C.text3, fontSize: 13 },

  // Manual entry
  manualRow: { flexDirection: 'row', gap: 10 },
  isbnInput: {
    flex: 1, backgroundColor: C.card, borderWidth: 1, borderColor: C.border,
    borderRadius: 10, padding: 13, color: C.text, fontSize: 15,
  },
  lookupBtn: {
    backgroundColor: C.accent, paddingHorizontal: 18,
    borderRadius: 10, justifyContent: 'center',
  },
  lookupBtnText: { color: C.bg, fontWeight: '700', fontSize: 14 },
  btnDisabled:   { opacity: 0.5 },

  hint: { color: 'rgba(255,255,255,0.35)', textAlign: 'center', fontSize: 13 },

  isbnBanner: {
    backgroundColor: C.surface, borderWidth: 1, borderColor: C.border,
    borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8,
  },
  isbnBannerText: { color: C.text2, fontSize: 12, textAlign: 'center' },
});
