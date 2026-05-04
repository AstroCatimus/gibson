/**
 * Gibson — Shelf Scan Screen.
 * Photograph a shelf → Claude Vision → instant GREEN/YELLOW/RED/GREY results.
 * Replaces the overnight YOLO pipeline with a 10-second Claude Sonnet call.
 *
 * Navigation: pushed from defrag tab with params { section, sessionId }
 */

import { useState, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  ActivityIndicator, Alert, Image,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { router, useLocalSearchParams } from 'expo-router';
import { api } from '../src/lib/api';

const BG     = '#0f0f1a';
const CARD   = '#13131f';
const ACCENT = '#e94560';
const GREEN  = '#2ecc71';
const YELLOW = '#f39c12';
const RED    = '#e74c3c';
const GREY   = '#555555';

const STATUS_COLORS = { GREEN, YELLOW, RED, GREY };
const STATUS_LABELS = {
  GREEN:  'Auto-verified',
  YELLOW: 'Location conflict',
  RED:    'Not in database',
  GREY:   'Spine unreadable',
};
const STATUS_ICONS = { GREEN: '✓', YELLOW: '⚠', RED: '✗', GREY: '?' };

export default function ShelfScanScreen() {
  const params     = useLocalSearchParams();
  const section    = params.section    || 'Unknown Section';
  const sessionId  = params.sessionId  || null;

  const [permission, requestPermission] = useCameraPermissions();
  const [scanning,   setScanning]       = useState(false);
  const [results,    setResults]        = useState(null);  // null = not yet scanned
  const [preview,    setPreview]        = useState(null);  // uri of last photo
  const cameraRef = useRef(null);

  if (!permission) return <View style={s.container} />;
  if (!permission.granted) {
    return (
      <View style={[s.container, s.center]}>
        <Text style={s.permText}>Camera access needed.</Text>
        <TouchableOpacity style={s.btn} onPress={requestPermission}>
          <Text style={s.btnText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  async function captureShelf() {
    if (!cameraRef.current || scanning) return;
    setScanning(true);
    setResults(null);
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.85,
        base64: true,
      });
      setPreview(photo.uri);
      const data = await api.shelfScan(photo.base64, section, sessionId);
      setResults(data);
    } catch (e) {
      Alert.alert('Scan failed', e.message);
    } finally {
      setScanning(false);
    }
  }

  function resetScan() {
    setResults(null);
    setPreview(null);
  }

  // ── Results view ─────────────────────────────────────────────
  if (results) {
    const { summary, green, yellow, red, grey } = results;
    return (
      <ScrollView style={s.container} contentContainerStyle={s.content}>

        {/* Preview thumbnail */}
        {preview && (
          <Image source={{ uri: preview }} style={s.previewThumb} resizeMode="cover" />
        )}

        {/* Summary pills */}
        <View style={s.summaryRow}>
          <SummaryPill status="GREEN"  count={summary.green}  />
          <SummaryPill status="YELLOW" count={summary.yellow} />
          <SummaryPill status="RED"    count={summary.red}    />
          <SummaryPill status="GREY"   count={summary.grey}   />
        </View>

        <Text style={s.autoNote}>
          {summary.green} book{summary.green !== 1 ? 's' : ''} auto-verified.
          {summary.yellow + summary.red + summary.grey > 0
            ? ` ${summary.yellow + summary.red + summary.grey} need attention.`
            : ' No action needed.'}
        </Text>

        {/* GREEN — collapsed, just the count */}
        {green.length > 0 && (
          <CollapsibleSection
            status="GREEN"
            items={green}
            renderItem={(item, i) => (
              <Text key={i} style={s.greenItem}>✓ {item.db_title || item.title}</Text>
            )}
          />
        )}

        {/* YELLOW — location conflicts, need resolution */}
        {yellow.length > 0 && (
          <View style={s.section}>
            <SectionHeader status="YELLOW" count={yellow.length} label="Location Conflicts" />
            {yellow.map((item, i) => (
              <ConflictCard
                key={i}
                item={item}
                onUpdateLocation={async () => {
                  await api.resolveConflict(item.stock_item_id, 'UPDATE_LOCATION', section);
                  setResults(prev => ({
                    ...prev,
                    yellow: prev.yellow.filter((_, j) => j !== i),
                    green:  [...prev.green, item],
                    summary: {
                      ...prev.summary,
                      yellow: prev.summary.yellow - 1,
                      green:  prev.summary.green + 1,
                    },
                  }));
                }}
                onReshelve={async () => {
                  await api.resolveConflict(item.stock_item_id, 'RETURN_TO_SECTION', null);
                  setResults(prev => ({
                    ...prev,
                    yellow: prev.yellow.filter((_, j) => j !== i),
                    summary: { ...prev.summary, yellow: prev.summary.yellow - 1 },
                  }));
                }}
              />
            ))}
          </View>
        )}

        {/* RED — not in database */}
        {red.length > 0 && (
          <View style={s.section}>
            <SectionHeader status="RED" count={red.length} label="Not in Database" />
            <Text style={s.sectionNote}>
              These books are on the shelf but have no record. They need to be catalogued.
            </Text>
            {red.map((item, i) => (
              <View key={i} style={[s.spineCard, { borderColor: RED + '44' }]}>
                <Text style={s.spineTitle}>{item.title || '—'}</Text>
                {item.author && <Text style={s.spineSub}>{item.author}</Text>}
                {item.isbn && <Text style={s.spineSub}>ISBN: {item.isbn}</Text>}
                <TouchableOpacity
                  style={s.scanBtn}
                  onPress={() => router.push('/')}
                >
                  <Text style={s.scanBtnText}>Scan this book →</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {/* GREY — unreadable spines */}
        {grey.length > 0 && (
          <View style={s.section}>
            <SectionHeader status="GREY" count={grey.length} label="Unreadable Spines" />
            <Text style={s.sectionNote}>
              Pull these books and photograph the front cover for identification.
            </Text>
            {grey.map((item, i) => (
              <View key={i} style={[s.spineCard, { borderColor: '#333' }]}>
                <Text style={[s.spineTitle, { color: '#666' }]}>
                  {item.title || 'Unreadable spine'}
                </Text>
                {item.notes && <Text style={s.spineSub}>{item.notes}</Text>}
              </View>
            ))}
          </View>
        )}

        {/* Actions */}
        <View style={s.footerBtns}>
          <TouchableOpacity style={s.rescanBtn} onPress={resetScan}>
            <Text style={s.rescanBtnText}>Scan Another Shelf</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.doneBtn} onPress={() => router.back()}>
            <Text style={s.doneBtnText}>Done</Text>
          </TouchableOpacity>
        </View>

      </ScrollView>
    );
  }

  // ── Camera view ───────────────────────────────────────────────
  return (
    <View style={s.container}>
      <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="back" />

      {/* Header */}
      <View style={s.camHeader}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={s.backBtn}>← Back</Text>
        </TouchableOpacity>
        <Text style={s.camSection}>{section}</Text>
      </View>

      {/* Guide overlay */}
      <View style={s.guideOverlay} pointerEvents="none">
        <View style={s.guideBox} />
        <Text style={s.guideText}>
          Fill the frame with book spines.{'\n'}
          Aim for 10–20 books per photo.
        </Text>
      </View>

      {/* Processing overlay */}
      {scanning && (
        <View style={s.processingOverlay}>
          <ActivityIndicator color={ACCENT} size="large" />
          <Text style={s.processingText}>Identifying spines with Claude Vision…</Text>
          <Text style={s.processingSubtext}>~10 seconds</Text>
        </View>
      )}

      {/* Capture button */}
      {!scanning && (
        <View style={s.camControls}>
          <Text style={s.camHint}>
            Stand back so all spines are visible and in focus.
          </Text>
          <TouchableOpacity style={s.captureBtn} onPress={captureShelf}>
            <View style={s.captureInner} />
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

// ── Sub-components ────────────────────────────────────────────

function SummaryPill({ status, count }) {
  const color = STATUS_COLORS[status];
  const icon  = STATUS_ICONS[status];
  return (
    <View style={[sp.pill, { borderColor: color, backgroundColor: color + '1a' }]}>
      <Text style={[sp.icon, { color }]}>{icon}</Text>
      <Text style={[sp.count, { color }]}>{count}</Text>
      <Text style={sp.label}>{status}</Text>
    </View>
  );
}
const sp = StyleSheet.create({
  pill: {
    flex: 1, alignItems: 'center', borderWidth: 1, borderRadius: 10,
    paddingVertical: 10,
  },
  icon:  { fontSize: 14, fontWeight: '700' },
  count: { fontSize: 22, fontWeight: '700', marginTop: 2 },
  label: { color: '#444', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 },
});

function SectionHeader({ status, count, label }) {
  const color = STATUS_COLORS[status];
  return (
    <View style={sh.row}>
      <View style={[sh.dot, { backgroundColor: color }]} />
      <Text style={[sh.label, { color }]}>{label}</Text>
      <Text style={[sh.count, { color }]}>{count}</Text>
    </View>
  );
}
const sh = StyleSheet.create({
  row:   { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  dot:   { width: 8, height: 8, borderRadius: 4, marginRight: 8 },
  label: { flex: 1, fontWeight: '700', fontSize: 14 },
  count: { fontSize: 13, fontWeight: '700' },
});

function CollapsibleSection({ status, items, renderItem }) {
  const [open, setOpen] = useState(false);
  const color = STATUS_COLORS[status];
  return (
    <View style={s.section}>
      <TouchableOpacity onPress={() => setOpen(o => !o)} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
        <View style={[sh.dot, { backgroundColor: color }]} />
        <Text style={[sh.label, { color }]}>{STATUS_LABELS[status]}</Text>
        <Text style={{ color: '#555', fontSize: 13 }}>{items.length}  {open ? '▲' : '▼'}</Text>
      </TouchableOpacity>
      {open && items.map(renderItem)}
    </View>
  );
}

function ConflictCard({ item, onUpdateLocation, onReshelve }) {
  return (
    <View style={[s.spineCard, { borderColor: YELLOW + '66' }]}>
      <Text style={s.spineTitle}>{item.db_title || item.title}</Text>
      <Text style={s.spineSub}>
        Record says: <Text style={{ color: YELLOW }}>{item.db_section || 'No section'}</Text>
        {' '}· Found in: <Text style={{ color: GREEN }}>{item.scanned_section}</Text>
      </Text>
      <View style={cc.btns}>
        <TouchableOpacity style={[cc.btn, { borderColor: GREEN }]} onPress={onUpdateLocation}>
          <Text style={[cc.txt, { color: GREEN }]}>Update Location</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[cc.btn, { borderColor: '#555' }]} onPress={onReshelve}>
          <Text style={[cc.txt, { color: '#555' }]}>Mark to Reshelve</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}
const cc = StyleSheet.create({
  btns: { flexDirection: 'row', gap: 8, marginTop: 10 },
  btn:  { borderWidth: 1, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6 },
  txt:  { fontSize: 12, fontWeight: '700' },
});

// ── Styles ────────────────────────────────────────────────────
const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  center:    { alignItems: 'center', justifyContent: 'center' },
  content:   { padding: 16, paddingBottom: 40 },

  permText: { color: '#fff', textAlign: 'center', margin: 20 },
  btn: { backgroundColor: ACCENT, padding: 14, borderRadius: 10, alignItems: 'center' },
  btnText: { color: '#fff', fontWeight: '600' },

  previewThumb: {
    width: '100%', height: 160, borderRadius: 10,
    marginBottom: 14, backgroundColor: '#0c0c17',
  },

  summaryRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  autoNote:   { color: '#666', fontSize: 13, marginBottom: 20, textAlign: 'center' },

  section:     { marginBottom: 20 },
  sectionNote: { color: '#555', fontSize: 12, marginBottom: 10, lineHeight: 16 },

  greenItem: { color: GREEN + 'cc', fontSize: 12, marginBottom: 4 },

  spineCard: {
    backgroundColor: CARD, borderRadius: 10,
    borderWidth: 1, padding: 12, marginBottom: 8,
  },
  spineTitle: { color: '#fff', fontSize: 14, fontWeight: '600', marginBottom: 4 },
  spineSub:   { color: '#555', fontSize: 12, marginBottom: 2 },
  scanBtn: {
    marginTop: 8, borderWidth: 1, borderColor: ACCENT,
    borderRadius: 6, padding: 7, alignItems: 'center',
  },
  scanBtnText: { color: ACCENT, fontSize: 12, fontWeight: '600' },

  footerBtns:    { flexDirection: 'row', gap: 12, marginTop: 8 },
  rescanBtn: {
    flex: 1, borderWidth: 1, borderColor: ACCENT,
    borderRadius: 12, padding: 14, alignItems: 'center',
  },
  rescanBtnText: { color: ACCENT, fontWeight: '700' },
  doneBtn:   { flex: 1, backgroundColor: ACCENT, borderRadius: 12, padding: 14, alignItems: 'center' },
  doneBtnText: { color: '#fff', fontWeight: '700' },

  // Camera
  camHeader: {
    position: 'absolute', top: 0, left: 0, right: 0,
    flexDirection: 'row', alignItems: 'center',
    paddingTop: 56, paddingHorizontal: 16, paddingBottom: 12,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  backBtn:    { color: ACCENT, fontSize: 14, marginRight: 16 },
  camSection: { color: '#fff', fontWeight: '700', fontSize: 16, flex: 1 },

  guideOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 120,
    alignItems: 'center', justifyContent: 'center',
  },
  guideBox: {
    width: '90%', height: '60%',
    borderWidth: 2, borderColor: 'rgba(255,255,255,0.35)',
    borderRadius: 8,
  },
  guideText: {
    color: 'rgba(255,255,255,0.7)', textAlign: 'center',
    fontSize: 13, marginTop: 14, lineHeight: 20,
  },

  processingOverlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.75)',
    alignItems: 'center', justifyContent: 'center', gap: 14,
  },
  processingText:    { color: '#fff', fontSize: 15, fontWeight: '600' },
  processingSubtext: { color: '#666', fontSize: 13 },

  camControls: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(13,13,25,0.95)',
    padding: 24, paddingBottom: 48, alignItems: 'center', gap: 16,
  },
  camHint: { color: '#555', fontSize: 13, textAlign: 'center' },
  captureBtn: {
    width: 72, height: 72, borderRadius: 36,
    borderWidth: 3, borderColor: '#fff',
    alignItems: 'center', justifyContent: 'center',
  },
  captureInner: {
    width: 58, height: 58, borderRadius: 29,
    backgroundColor: '#fff',
  },
});
