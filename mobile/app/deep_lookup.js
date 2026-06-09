/**
 * Gibson — Deep Lookup Screen.
 * Rare book assessment: edition, value, signatures, anomalies.
 *
 * Flow:
 *  1. Stage 1 trigger (free, instant) — shows suggestion card with reasons
 *  2. Dealer taps Run — Stage 2 triage + Stage 3 search + assess (~20-60s)
 *  3. If needs_more_photos — shows photo request, dealer provides or skips
 *  4. Results: dealer_action, value range, edition, physical checks, signature
 */

import { useState, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, Linking,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { api } from '../src/lib/api';
import { getScanPhotoArray } from '../src/lib/scan_session';
import { C } from '../src/lib/theme';

// Build the research_result shape the new pipeline expects from the params
// passed by identify.js. Confidence is set to 1.0 for confirmed fields.
function buildResearchResult(title, author, publisher, year, isbn) {
  return {
    title:             { value: title || '',       confidence: title    ? 1.0 : 0.0, source: 'identification' },
    author:            { value: author || '',      confidence: author   ? 1.0 : 0.0, source: 'identification' },
    publisher:         { value: publisher || null, confidence: publisher ? 0.9 : 0.0, source: 'identification' },
    year:              { value: year ? parseInt(year) : null, confidence: year ? 0.9 : 0.0, source: 'identification' },
    isbn_13:           { value: isbn || null,      confidence: isbn     ? 1.0 : 0.0, source: 'identification' },
    edition_statement: { value: null,              confidence: 0.0,                  source: 'identification' },
    subjects:          { value: [],                confidence: 0.0,                  source: 'identification' },
    page_count:        { value: null,              confidence: 0.0,                  source: 'identification' },
    pricing: {
      suggested_price: null,
      range_low:       null,
      range_high:      null,
      comp_count:      0,
      sources:         [],
    },
    overall_confidence: title && author ? 0.9 : 0.5,
    routing: isbn ? 'CONFIRM' : 'REVIEW',
  };
}

export default function DeepLookupScreen() {
  const params = useLocalSearchParams();
  const { title, author, publisher, year, isbn, stockItemId } = params;

  const [phase, setPhase]       = useState('trigger');   // trigger | running | result | photo_request
  const [reasons, setReasons]   = useState([]);          // Stage 1 reasons
  const [result, setResult]     = useState(null);
  const [running, setRunning]   = useState(false);
  const [status, setStatus]     = useState('');

  const scanImages    = useRef(getScanPhotoArray());
  const researchResult = useRef(buildResearchResult(title, author, publisher, year, isbn));

  // Stage 1 — run on mount, free
  useEffect(() => {
    (async () => {
      try {
        const data = await api.deepLookupTrigger(researchResult.current);
        setReasons(data.reasons || []);
        setPhase('trigger');
      } catch {
        // If trigger fails just show the run button anyway
        setPhase('trigger');
      }
    })();
  }, []);

  async function handleRun() {
    setRunning(true);
    setStatus('Checking collectibility…');
    try {
      // Stagger status messages while waiting
      const timer1 = setTimeout(() => setStatus('Searching auction records…'), 5000);
      const timer2 = setTimeout(() => setStatus('Analysing edition points…'), 15000);
      const timer3 = setTimeout(() => setStatus('Almost done…'), 30000);

      const data = await api.deepLookupRun(researchResult.current, scanImages.current);

      clearTimeout(timer1);
      clearTimeout(timer2);
      clearTimeout(timer3);

      if (data.stage_reached === 2) {
        // Stage 2 SKIP — show dealer_action as a plain result
        setResult({ _skipped: true, reason: data.dealer_action });
        setPhase('result');
        return;
      }

      setResult(data);
      setPhase(data.needs_more_photos ? 'photo_request' : 'result');
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setRunning(false);
      setStatus('');
    }
  }

  async function handlePhotoProvided(photoBase64) {
    setRunning(true);
    setStatus('Updating assessment…');
    try {
      const data = await api.deepLookupFollowup(result, photoBase64, researchResult.current);
      setResult(data);
      setPhase('result');
    } catch (e) {
      Alert.alert('Error', e.message);
      setPhase('result'); // Show original result on failure
    } finally {
      setRunning(false);
      setStatus('');
    }
  }

  async function promptForPhoto() {
    Alert.alert(
      result.photo_request || 'One more photo needed',
      'Photograph the requested page or skip to see the current assessment.',
      [
        {
          text: 'Take Photo',
          onPress: async () => {
            const perm = await ImagePicker.requestCameraPermissionsAsync();
            if (!perm.granted) return;
            const res = await ImagePicker.launchCameraAsync({ quality: 0.8, base64: true });
            if (!res.canceled) await handlePhotoProvided(res.assets[0].base64);
          },
        },
        {
          text: 'Skip',
          onPress: () => setPhase('result'),
        },
      ],
    );
  }

  // ── Loading overlay ──────────────────────────────────────────
  if (running) {
    return (
      <View style={s.loadingScreen}>
        <ActivityIndicator color={C.accent} size="large" />
        <Text style={s.loadingStatus}>{status}</Text>
      </View>
    );
  }

  // ── Photo request ────────────────────────────────────────────
  if (phase === 'photo_request' && result) {
    return (
      <View style={s.photoScreen}>
        <View style={s.photoCard}>
          <Text style={s.photoIcon}>📄</Text>
          <Text style={s.photoTitle}>One more photo needed</Text>
          <Text style={s.photoRequest}>{result.photo_request}</Text>
          <TouchableOpacity style={s.photoBtn} onPress={promptForPhoto}>
            <Text style={s.photoBtnText}>📷  Take Photo</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.photoSkip} onPress={() => setPhase('result')}>
            <Text style={s.photoSkipText}>Skip — show current assessment</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // ── Stage 1 trigger card ─────────────────────────────────────
  if (phase === 'trigger') {
    const hasReasons = reasons.length > 0;
    return (
      <View style={s.triggerScreen}>
        <View style={s.triggerCard}>
          <Text style={s.triggerIcon}>{hasReasons ? '⚡' : '📚'}</Text>
          <Text style={s.triggerTitle}>
            {hasReasons ? 'Potential collectible' : 'Deep Lookup'}
          </Text>
          {hasReasons ? (
            <>
              <Text style={s.triggerSub}>Flagged for these reasons:</Text>
              {reasons.map((r, i) => (
                <View key={i} style={s.reasonRow}>
                  <Text style={s.reasonDot}>·</Text>
                  <Text style={s.reasonText}>{r}</Text>
                </View>
              ))}
              <Text style={s.triggerNote}>
                Deep lookup searches auction records, edition guides, and analyses your photos.
                Takes 20–60 seconds.
              </Text>
            </>
          ) : (
            <Text style={s.triggerNote}>
              No automatic flags for this book. You can still run a deep lookup to check for
              signed copies, first edition points, or unusual value.
            </Text>
          )}
          <TouchableOpacity style={s.runBtn} onPress={handleRun}>
            <Text style={s.runBtnText}>Run Deep Lookup</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.backLink} onPress={() => router.back()}>
            <Text style={s.backLinkText}>← Back</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // ── Skipped at Stage 2 ───────────────────────────────────────
  if (result?._skipped) {
    return (
      <View style={s.triggerScreen}>
        <View style={s.triggerCard}>
          <Text style={s.triggerIcon}>📚</Text>
          <Text style={s.triggerTitle}>Nothing significant found</Text>
          <Text style={s.triggerNote}>{result.reason}</Text>
          <TouchableOpacity style={s.backLink} onPress={() => router.back()}>
            <Text style={s.backLinkText}>← Back</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  if (!result) return null;

  const hasAnomaly  = result.anomaly_found;
  const hasValue    = result.anomaly_value_low != null || result.anomaly_value_high != null;
  const hasSig      = result.signature_found;
  const conf        = result.confidence || 0;
  const confColor   = conf >= 0.7 ? C.accent : conf >= 0.4 ? C.yellow : C.text3;

  // ── Full results ─────────────────────────────────────────────
  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* Header */}
      <View style={s.headerCard}>
        <Text style={s.headerTitle} numberOfLines={2}>{title || 'Book'}</Text>
        {author ? (
          <Text style={s.headerSub}>{author}{year ? ` · ${year}` : ''}</Text>
        ) : null}
        <View style={s.confRow}>
          <View style={[s.confPill, { borderColor: confColor, backgroundColor: confColor + '18' }]}>
            <Text style={[s.confText, { color: confColor }]}>
              {conf >= 0.7 ? '⚡ High confidence' : conf >= 0.4 ? '◈ Medium confidence' : '· Low confidence'}
            </Text>
          </View>
          {result.anomaly_type ? (
            <View style={[s.typePill]}>
              <Text style={s.typeText}>{result.anomaly_type.replace('_', ' ')}</Text>
            </View>
          ) : null}
        </View>
      </View>

      {/* Dealer action — the main instruction */}
      {result.dealer_action ? (
        <View style={[s.card, s.actionCard]}>
          <Text style={s.actionLabel}>WHAT TO DO NOW</Text>
          <Text style={s.actionText}>{result.dealer_action}</Text>
        </View>
      ) : null}

      {/* Anomaly / value */}
      {hasAnomaly && hasValue ? (
        <View style={[s.card, s.valueCard]}>
          <Text style={s.valueLabel}>ASSESSED VALUE  ·  deep lookup</Text>
          <Text style={s.valueRange}>
            {result.anomaly_value_low != null && result.anomaly_value_high != null
              ? `$${result.anomaly_value_low.toFixed(0)} – $${result.anomaly_value_high.toFixed(0)}`
              : result.anomaly_value_low != null
                ? `from $${result.anomaly_value_low.toFixed(0)}`
                : `up to $${result.anomaly_value_high.toFixed(0)}`}
          </Text>
          {result.baseline_value != null ? (
            <Text style={s.baselineText}>
              Baseline (standard copy): ${result.baseline_value.toFixed(0)}
            </Text>
          ) : null}
          {result.anomaly_detail ? (
            <Text style={s.anomalyDetail}>{result.anomaly_detail}</Text>
          ) : null}
        </View>
      ) : null}

      {/* Edition assessment */}
      {result.edition_assessment ? (
        <View style={s.card}>
          <Text style={s.cardLabel}>Edition Assessment</Text>
          <Text style={s.editionText}>{result.edition_assessment}</Text>
        </View>
      ) : null}

      {/* Signature */}
      {hasSig ? (
        <View style={[s.card, s.sigCard]}>
          <Text style={s.cardLabel}>Signature / Inscription Detected</Text>
          {result.signature_detail ? (
            <Text style={s.sigDetail}>"{result.signature_detail}"</Text>
          ) : null}
          <View style={s.sigWarning}>
            <Text style={s.sigWarningIcon}>⚠</Text>
            <Text style={s.sigWarningText}>
              Verify authenticity with a specialist before pricing as a signed copy.
              Gibson cannot authenticate signatures.
            </Text>
          </View>
        </View>
      ) : null}

      {/* Physical checks */}
      {result.physical_checks?.length > 0 ? (
        <View style={s.card}>
          <Text style={s.cardLabel}>Check on the Physical Copy</Text>
          {result.physical_checks.map((check, i) => (
            <View key={i} style={s.checkRow}>
              <Text style={s.checkNum}>{i + 1}</Text>
              <Text style={s.checkText}>{check}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {/* Sources */}
      {result.sources_used?.length > 0 ? (
        <View style={s.card}>
          <Text style={s.cardLabel}>Sources Used</Text>
          {result.sources_used.map((src, i) => (
            <Text key={i} style={s.sourceItem}>· {src}</Text>
          ))}
        </View>
      ) : null}

      {/* Stage / token meta — small, bottom */}
      <Text style={s.meta}>
        Stage {result.stage_reached} · {result.tokens_used?.toLocaleString()} tokens · {result.elapsed_seconds}s
      </Text>

      <TouchableOpacity style={s.backBtn} onPress={() => router.back()}>
        <Text style={s.backBtnText}>← Back to identification</Text>
      </TouchableOpacity>

    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  content:   { padding: 16, paddingBottom: 48 },

  loadingScreen: {
    flex: 1, backgroundColor: C.bg,
    alignItems: 'center', justifyContent: 'center', padding: 32,
  },
  loadingStatus: { color: C.text, fontSize: 15, fontWeight: '600', marginTop: 20 },

  // Trigger screen
  triggerScreen: {
    flex: 1, backgroundColor: C.bg,
    alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  triggerCard: {
    backgroundColor: C.card, borderRadius: 16,
    padding: 24, borderWidth: 1, borderColor: C.border,
    alignItems: 'center', width: '100%',
  },
  triggerIcon:  { fontSize: 40, marginBottom: 12 },
  triggerTitle: { color: C.text, fontSize: 18, fontWeight: '700', marginBottom: 8 },
  triggerSub:   { color: C.text3, fontSize: 12, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.8 },
  reasonRow:    { flexDirection: 'row', gap: 8, marginBottom: 6, alignSelf: 'stretch' },
  reasonDot:    { color: C.accent, fontSize: 16, width: 12, textAlign: 'center' },
  reasonText:   { flex: 1, color: C.text2, fontSize: 13, lineHeight: 20 },
  triggerNote:  { color: C.text3, fontSize: 12, lineHeight: 18, textAlign: 'center', marginVertical: 16 },
  runBtn: {
    backgroundColor: C.accent, padding: 14, borderRadius: 10,
    width: '100%', alignItems: 'center', marginBottom: 10,
  },
  runBtnText:  { color: C.bg, fontWeight: '700', fontSize: 14 },
  backLink:    { padding: 10 },
  backLinkText: { color: C.text3, fontSize: 13 },

  // Photo request
  photoScreen: {
    flex: 1, backgroundColor: C.bg,
    alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  photoCard: {
    backgroundColor: C.card, borderRadius: 16,
    padding: 24, borderWidth: 1, borderColor: C.border,
    alignItems: 'center', width: '100%',
  },
  photoIcon:    { fontSize: 36, marginBottom: 12 },
  photoTitle:   { color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 8 },
  photoRequest: { color: C.text2, fontSize: 13, lineHeight: 20, textAlign: 'center', marginBottom: 20 },
  photoBtn: {
    backgroundColor: C.accent, padding: 14, borderRadius: 10,
    width: '100%', alignItems: 'center', marginBottom: 10,
  },
  photoBtnText: { color: C.bg, fontWeight: '700', fontSize: 14 },
  photoSkip:    { padding: 10 },
  photoSkipText: { color: C.text3, fontSize: 13 },

  // Cards
  card: {
    backgroundColor: C.card, borderRadius: 12,
    padding: 16, marginBottom: 12,
    borderWidth: 1, borderColor: C.border,
  },
  cardLabel: {
    color: C.text3, fontSize: 10,
    textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 12,
  },

  // Header
  headerCard: {
    backgroundColor: C.card, borderRadius: 12,
    padding: 16, marginBottom: 12,
    borderWidth: 1, borderColor: C.border,
  },
  headerTitle: { color: C.text, fontSize: 18, fontWeight: '700', lineHeight: 24 },
  headerSub:   { color: C.text2, fontSize: 13, marginTop: 4 },
  confRow:     { flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' },
  confPill: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 999, borderWidth: 1,
  },
  confText: { fontSize: 12, fontWeight: '600' },
  typePill: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 999, borderWidth: 1,
    borderColor: C.accent, backgroundColor: C.accentBg,
  },
  typeText: { fontSize: 12, fontWeight: '600', color: C.accent },

  // Action card
  actionCard: { borderColor: C.accent },
  actionLabel: {
    color: C.accentDim, fontSize: 10,
    textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8,
  },
  actionText: { color: C.text, fontSize: 15, lineHeight: 22, fontWeight: '500' },

  // Value card
  valueCard: { borderColor: C.accent, backgroundColor: C.accentBg },
  valueLabel: {
    color: C.accentDim, fontSize: 10,
    textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8,
  },
  valueRange:    { color: C.text, fontSize: 36, fontWeight: '800', letterSpacing: -0.5 },
  baselineText:  { color: C.text3, fontSize: 12, marginTop: 6 },
  anomalyDetail: { color: C.text2, fontSize: 12, marginTop: 8, lineHeight: 18 },

  // Edition
  editionText: { color: C.text2, fontSize: 13, lineHeight: 20 },

  // Signature
  sigCard:   { borderColor: C.yellow + '66' },
  sigDetail: { color: C.text, fontSize: 14, fontStyle: 'italic', marginBottom: 12, lineHeight: 22 },
  sigWarning: {
    flexDirection: 'row', gap: 8,
    backgroundColor: C.yellowBg, borderRadius: 8, padding: 10,
  },
  sigWarningIcon: { color: C.yellow, fontSize: 14 },
  sigWarningText: { flex: 1, color: C.text2, fontSize: 12, lineHeight: 18 },

  // Physical checks
  checkRow: { flexDirection: 'row', gap: 10, marginBottom: 10, alignItems: 'flex-start' },
  checkNum: {
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: C.accentBg, borderWidth: 1, borderColor: C.accent,
    color: C.accent, fontSize: 11, fontWeight: '700',
    textAlign: 'center', lineHeight: 22,
  },
  checkText: { flex: 1, color: C.text, fontSize: 13, lineHeight: 20 },

  // Sources
  sourceItem: { color: C.text3, fontSize: 12, lineHeight: 20 },

  // Meta / back
  meta: { color: C.text3, fontSize: 11, textAlign: 'center', marginTop: 8, marginBottom: 4 },
  backBtn: { alignItems: 'center', padding: 12 },
  backBtnText: { color: C.text3, fontSize: 13 },
});
