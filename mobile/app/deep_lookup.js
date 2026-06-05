/**
 * Gibson — Deep Lookup Screen.
 * Rare book assessment: edition, value, signatures, sources.
 *
 * Flow:
 *  1. Runs Stage 2 triage (Sonnet, metadata-only, cheap)
 *  2. If proceed: runs Stage 3 full lookup (Sonnet + web search + images)
 *  3. If Claude needs one more photo: shows photo request
 *  4. Results: assessed value vs Gibson price, edition notes, sources
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

export default function DeepLookupScreen() {
  const params = useLocalSearchParams();
  const { title, author, publisher, year, isbn, stockItemId } = params;

  const [loading, setLoading]     = useState(true);
  const [status, setStatus]       = useState('Checking collectibility…');
  const [result, setResult]       = useState(null);
  const [saved, setSaved]         = useState(false);
  const [saving, setSaving]       = useState(false);
  const [photoLoading, setPhotoLoading] = useState(false);

  // Only ever use the photos that were taken during the scan
  const scanImages = useRef(getScanPhotoArray());

  useEffect(() => { runLookup(scanImages.current, null); }, []);

  async function runLookup(images, additionalImage) {
    setLoading(true);
    setResult(null);
    try {
      setStatus('Checking collectibility…');
      const data = await api.deepLookup({
        title:            title || null,
        author:           author || null,
        publisher:        publisher || null,
        publication_year: year ? parseInt(year) : null,
        isbn_13:          isbn || null,
        images:           images || [],
        additional_image: additionalImage || null,
        stock_item_id:    stockItemId || null,
        save_to_item:     false,
      });

      if (!data.triage_proceed) {
        setResult({ _not_collectible: true, reason: data.triage_reason || data.significance_summary });
        return;
      }

      setStatus('Researching edition and value…');
      setResult(data);
    } catch (e) {
      Alert.alert('Error', e.message);
      router.back();
    } finally {
      setLoading(false);
      setStatus('');
    }
  }

  async function handlePhotoRequest() {
    Alert.alert('Take a photo', result.photo_request_reason || '', [
      {
        text: 'Camera',
        onPress: async () => {
          const perm = await ImagePicker.requestCameraPermissionsAsync();
          if (!perm.granted) return;
          const res = await ImagePicker.launchCameraAsync({ quality: 0.8, base64: true });
          if (!res.canceled) {
            setPhotoLoading(true);
            await runLookup(scanImages.current, res.assets[0].base64);
            setPhotoLoading(false);
          }
        },
      },
      {
        text: 'Skip',
        onPress: async () => {
          // Re-run without additional image — server won't ask again
          setPhotoLoading(true);
          const r = { ...result, needs_photo: false };
          setResult(r);
          setPhotoLoading(false);
        },
      },
    ]);
  }

  async function handleSave() {
    if (!stockItemId) {
      Alert.alert('No item', 'Findings can only be saved after the book is confirmed into inventory.');
      return;
    }
    setSaving(true);
    try {
      await api.deepLookup({
        title:            title || null,
        author:           author || null,
        publisher:        publisher || null,
        publication_year: year ? parseInt(year) : null,
        isbn_13:          isbn || null,
        images:           scanImages.current,
        stock_item_id:    stockItemId,
        save_to_item:     true,
      });
      setSaved(true);
    } catch (e) {
      Alert.alert('Error saving', e.message);
    } finally {
      setSaving(false);
    }
  }

  // ── Loading state ────────────────────────────────────────────
  if (loading) {
    return (
      <View style={s.loadingScreen}>
        <ActivityIndicator color={C.accent} size="large" />
        <Text style={s.loadingStatus}>{status}</Text>
        <Text style={s.loadingHint}>Searching auction records and edition guides…</Text>
      </View>
    );
  }

  // ── Not collectible ──────────────────────────────────────────
  if (result?._not_collectible) {
    return (
      <View style={s.loadingScreen}>
        <Text style={s.notCollectibleIcon}>📚</Text>
        <Text style={s.notCollectibleTitle}>Nothing significant found</Text>
        <Text style={s.notCollectibleText}>{result.reason || 'This appears to be a standard copy with no notable collectible value.'}</Text>
        <TouchableOpacity style={s.backBtn} onPress={() => router.back()}>
          <Text style={s.backBtnText}>← Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Photo request ────────────────────────────────────────────
  if (result?.needs_photo && !photoLoading) {
    return (
      <View style={s.photoRequestScreen}>
        <View style={s.photoRequestCard}>
          <Text style={s.photoRequestIcon}>📄</Text>
          <Text style={s.photoRequestPage}>{result.photo_request_page || 'One more page'}</Text>
          <Text style={s.photoRequestReason}>{result.photo_request_reason}</Text>
          <TouchableOpacity style={s.photoTakeBtn} onPress={handlePhotoRequest}>
            <Text style={s.photoTakeBtnText}>📷  Take Photo</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.photoSkipBtn} onPress={() => setResult({ ...result, needs_photo: false })}>
            <Text style={s.photoSkipBtnText}>Skip — show results anyway</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  if (!result) return null;

  const hasValue  = result.assessed_value_low != null || result.assessed_value_high != null;
  const djWorth   = result.value_with_dj || result.value_without_dj;
  const hasSig    = result.signature_detected;
  const isFirst   = result.edition_printing === 'first';
  const score     = result.significance_score || 0;
  const scoreColor = score >= 0.7 ? C.accent : score >= 0.4 ? C.yellow : C.text3;

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* Header */}
      <View style={s.headerCard}>
        <Text style={s.headerTitle} numberOfLines={2}>{title || 'Book'}</Text>
        {author ? <Text style={s.headerAuthor}>{author}{year ? ` · ${year}` : ''}</Text> : null}
        <View style={s.scoreRow}>
          <View style={[s.scorePill, { borderColor: scoreColor, backgroundColor: scoreColor + '18' }]}>
            <Text style={[s.scoreText, { color: scoreColor }]}>
              {score >= 0.7 ? '⚡ High significance' : score >= 0.4 ? '◈ Moderate significance' : '· Low significance'}
            </Text>
          </View>
        </View>
        {result.significance_summary ? (
          <Text style={s.summaryText}>{result.significance_summary}</Text>
        ) : null}
      </View>

      {/* Assessed Value */}
      {hasValue && (
        <View style={s.assessedCard}>
          <Text style={s.assessedLabel}>ASSESSED VALUE  ·  deep lookup</Text>
          <Text style={s.assessedRange}>
            {result.assessed_value_low != null && result.assessed_value_high != null
              ? `$${result.assessed_value_low.toFixed(0)} – $${result.assessed_value_high.toFixed(0)}`
              : result.assessed_value_low != null
                ? `from $${result.assessed_value_low.toFixed(0)}`
                : `up to $${result.assessed_value_high.toFixed(0)}`}
          </Text>
          {result.assessed_value_reasoning ? (
            <Text style={s.assessedReasoning}>{result.assessed_value_reasoning}</Text>
          ) : null}
          {djWorth && (
            <View style={s.djRow}>
              {result.value_with_dj ? (
                <View style={s.djPill}>
                  <Text style={s.djPillLabel}>With DJ</Text>
                  <Text style={s.djPillValue}>{result.value_with_dj}</Text>
                </View>
              ) : null}
              {result.value_without_dj ? (
                <View style={[s.djPill, s.djPillDim]}>
                  <Text style={[s.djPillLabel, { color: C.text3 }]}>Without DJ</Text>
                  <Text style={[s.djPillValue, { color: C.text2 }]}>{result.value_without_dj}</Text>
                </View>
              ) : null}
            </View>
          )}
          {result.value_source_url ? (
            <TouchableOpacity onPress={() => Linking.openURL(result.value_source_url)}>
              <Text style={s.sourceLink}>View source ↗</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      )}

      {/* Gibson Suggested Price (from routing params or prior pricing) */}
      <View style={s.gibsonCard}>
        <Text style={s.gibsonLabel}>GIBSON SUGGESTED PRICE</Text>
        <Text style={s.gibsonNote}>Set before deep lookup — consider revising if assessed value differs significantly.</Text>
      </View>

      {/* Edition assessment */}
      {(result.edition_evidence?.length > 0 || result.edition_printing !== 'unknown') && (
        <View style={s.card}>
          <Text style={s.cardLabel}>Edition Assessment</Text>
          <View style={s.editionRow}>
            <Text style={[s.editionPrinting, isFirst && { color: C.accent }]}>
              {result.edition_printing === 'first' ? 'Likely First Edition'
                : result.edition_printing === 'later' ? 'Later Printing'
                : 'Edition Unknown'}
            </Text>
            <View style={[s.confBadge, {
              backgroundColor: result.edition_confidence === 'high' ? C.greenBg
                : result.edition_confidence === 'medium' ? C.accentBg : C.surface,
              borderColor: result.edition_confidence === 'high' ? C.green
                : result.edition_confidence === 'medium' ? C.accent : C.border,
            }]}>
              <Text style={[s.confBadgeText, {
                color: result.edition_confidence === 'high' ? C.green
                  : result.edition_confidence === 'medium' ? C.accent : C.text3,
              }]}>
                {result.edition_confidence} confidence
              </Text>
            </View>
          </View>
          {result.edition_evidence?.map((e, i) => (
            <View key={i} style={s.bulletRow}>
              <Text style={s.bullet}>·</Text>
              <Text style={s.bulletText}>{e}</Text>
            </View>
          ))}
        </View>
      )}

      {/* What to look for */}
      {result.points_to_check?.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardLabel}>Check on the Physical Copy</Text>
          {result.points_to_check.map((pt, i) => (
            <View key={i} style={s.checkRow}>
              <Text style={s.checkNum}>{i + 1}</Text>
              <Text style={s.checkText}>{pt}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Signature / inscription */}
      {hasSig && (
        <View style={[s.card, s.sigCard]}>
          <Text style={s.cardLabel}>
            {result.signature_type === 'signed' ? 'Signed Copy'
              : result.signature_type === 'inscribed' ? 'Inscribed Copy'
              : result.signature_type === 'association' ? 'Association Copy'
              : result.signature_type === 'bookplate' ? 'Bookplate Present'
              : 'Inscription Detected'}
          </Text>
          {result.signature_transcription ? (
            <Text style={s.sigTranscription}>"{result.signature_transcription}"</Text>
          ) : null}
          <View style={s.sigWarning}>
            <Text style={s.sigWarningIcon}>⚠</Text>
            <Text style={s.sigWarningText}>{result.signature_auth_note}</Text>
          </View>
        </View>
      )}

      {/* Author significance */}
      {(result.author_significance || result.author_awards?.length > 0) && (
        <View style={s.card}>
          <Text style={s.cardLabel}>Author Significance</Text>
          {result.author_significance ? (
            <Text style={s.authorSig}>{result.author_significance}</Text>
          ) : null}
          {result.author_awards?.map((award, i) => (
            <View key={i} style={s.bulletRow}>
              <Text style={s.bullet}>◆</Text>
              <Text style={s.bulletText}>{award}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Unverified claims — warning style */}
      {result.unverified_claims?.length > 0 && (
        <View style={[s.card, s.unverifiedCard]}>
          <Text style={[s.cardLabel, { color: C.yellow }]}>⚠ Unverified — Confirm Physically</Text>
          <Text style={s.unverifiedNote}>
            The following came from Gibson's training knowledge and could not be confirmed via web search.
            Verify against the physical book before pricing.
          </Text>
          {result.unverified_claims.map((claim, i) => (
            <View key={i} style={s.bulletRow}>
              <Text style={[s.bullet, { color: C.yellow }]}>!</Text>
              <Text style={[s.bulletText, { color: C.text2 }]}>{claim}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Sources */}
      {result.sources?.length > 0 && (
        <View style={s.card}>
          <Text style={s.cardLabel}>Sources</Text>
          {result.sources.map((src, i) => (
            <View key={i} style={s.sourceRow}>
              <View style={s.sourceMain}>
                <Text style={s.sourceTitle}>{src.title}</Text>
                <Text style={s.sourceReasoning}>{src.reasoning}</Text>
              </View>
              {src.url ? (
                <TouchableOpacity onPress={() => Linking.openURL(src.url)} style={s.sourceLinkBtn}>
                  <Text style={s.sourceLinkBtnText}>↗</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          ))}
        </View>
      )}

      {/* Save button */}
      {stockItemId ? (
        <TouchableOpacity
          style={[s.saveBtn, (saving || saved) && s.btnDisabled]}
          onPress={handleSave}
          disabled={saving || saved}
        >
          {saving
            ? <ActivityIndicator color={C.bg} />
            : <Text style={s.saveBtnText}>
                {saved ? '✓ Saved to Item' : 'Save Findings to Item'}
              </Text>
          }
        </TouchableOpacity>
      ) : null}

      <TouchableOpacity style={s.backBtnBottom} onPress={() => router.back()}>
        <Text style={s.backBtnBottomText}>← Back to identification</Text>
      </TouchableOpacity>

    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  content:   { padding: 16, paddingBottom: 48 },

  // Loading / not found screens
  loadingScreen: {
    flex: 1, backgroundColor: C.bg,
    alignItems: 'center', justifyContent: 'center', padding: 32,
  },
  loadingStatus: { color: C.text, fontSize: 15, fontWeight: '600', marginTop: 20 },
  loadingHint:   { color: C.text3, fontSize: 12, marginTop: 8, textAlign: 'center' },

  notCollectibleIcon:  { fontSize: 48, marginBottom: 16 },
  notCollectibleTitle: { color: C.text, fontSize: 18, fontWeight: '700', marginBottom: 8 },
  notCollectibleText:  { color: C.text2, fontSize: 14, textAlign: 'center', lineHeight: 22 },
  backBtn: { marginTop: 24, padding: 12 },
  backBtnText: { color: C.accent, fontSize: 14 },

  // Photo request screen
  photoRequestScreen: {
    flex: 1, backgroundColor: C.bg,
    alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  photoRequestCard: {
    backgroundColor: C.card, borderRadius: 16,
    padding: 24, borderWidth: 1, borderColor: C.border,
    alignItems: 'center', width: '100%',
  },
  photoRequestIcon:   { fontSize: 36, marginBottom: 12 },
  photoRequestPage:   { color: C.accent, fontSize: 16, fontWeight: '700', marginBottom: 8 },
  photoRequestReason: { color: C.text2, fontSize: 14, textAlign: 'center', lineHeight: 20, marginBottom: 24 },
  photoTakeBtn: {
    backgroundColor: C.accent, padding: 14, borderRadius: 10,
    width: '100%', alignItems: 'center', marginBottom: 10,
  },
  photoTakeBtnText: { color: C.bg, fontWeight: '700', fontSize: 14 },
  photoSkipBtn: { padding: 10 },
  photoSkipBtnText: { color: C.text3, fontSize: 13 },

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
  headerTitle:  { color: C.text, fontSize: 18, fontWeight: '700', lineHeight: 24 },
  headerAuthor: { color: C.text2, fontSize: 13, marginTop: 4 },
  scoreRow:     { flexDirection: 'row', marginTop: 12, marginBottom: 8 },
  scorePill: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 999, borderWidth: 1,
  },
  scoreText:    { fontSize: 12, fontWeight: '600' },
  summaryText:  { color: C.text2, fontSize: 13, lineHeight: 20, marginTop: 4 },

  // Assessed value card — amber gold
  assessedCard: {
    backgroundColor: C.accentBg, borderRadius: 12,
    padding: 16, marginBottom: 12,
    borderWidth: 1, borderColor: C.accent,
  },
  assessedLabel: {
    color: C.accentDim, fontSize: 10,
    textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 8,
  },
  assessedRange: {
    color: C.text, fontSize: 36, fontWeight: '800', letterSpacing: -0.5,
  },
  assessedReasoning: { color: C.text2, fontSize: 12, marginTop: 8, lineHeight: 18 },
  djRow:  { flexDirection: 'row', gap: 8, marginTop: 12 },
  djPill: {
    flex: 1, backgroundColor: C.surface,
    borderRadius: 8, padding: 10,
    borderWidth: 1, borderColor: C.accent,
  },
  djPillDim: { borderColor: C.border },
  djPillLabel: { color: C.accent, fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.8 },
  djPillValue: { color: C.text, fontSize: 15, fontWeight: '700', marginTop: 2 },
  sourceLink: { color: C.accentDim, fontSize: 11, marginTop: 10 },

  // Gibson price card
  gibsonCard: {
    backgroundColor: C.surface, borderRadius: 12,
    padding: 14, marginBottom: 12,
    borderWidth: 1, borderColor: C.border,
  },
  gibsonLabel: {
    color: C.text3, fontSize: 10,
    textTransform: 'uppercase', letterSpacing: 1.2, marginBottom: 6,
  },
  gibsonNote: { color: C.text3, fontSize: 12, lineHeight: 17 },

  // Edition
  editionRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  editionPrinting: { color: C.text, fontSize: 15, fontWeight: '700', flex: 1 },
  confBadge: {
    paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: 6, borderWidth: 1,
  },
  confBadgeText: { fontSize: 11, fontWeight: '600' },

  // Bullets
  bulletRow: { flexDirection: 'row', gap: 8, marginBottom: 6 },
  bullet:    { color: C.accent, fontSize: 14, width: 12, textAlign: 'center', marginTop: 1 },
  bulletText: { flex: 1, color: C.text2, fontSize: 13, lineHeight: 20 },

  // Points to check
  checkRow: { flexDirection: 'row', gap: 10, marginBottom: 10, alignItems: 'flex-start' },
  checkNum: {
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: C.accentBg, borderWidth: 1, borderColor: C.accent,
    alignItems: 'center', justifyContent: 'center',
    color: C.accent, fontSize: 11, fontWeight: '700', textAlign: 'center', lineHeight: 22,
  },
  checkText: { flex: 1, color: C.text, fontSize: 13, lineHeight: 20 },

  // Signature
  sigCard: { borderColor: C.yellowBg },
  sigTranscription: {
    color: C.text, fontSize: 15, fontStyle: 'italic',
    marginBottom: 12, lineHeight: 22,
  },
  sigWarning: {
    flexDirection: 'row', gap: 8,
    backgroundColor: C.yellowBg, borderRadius: 8, padding: 10,
  },
  sigWarningIcon: { color: C.yellow, fontSize: 14 },
  sigWarningText: { flex: 1, color: C.text2, fontSize: 12, lineHeight: 18 },

  // Author
  authorSig: { color: C.text2, fontSize: 13, lineHeight: 20, marginBottom: 8 },

  // Unverified
  unverifiedCard: { borderColor: C.yellow + '66' },
  unverifiedNote: { color: C.text2, fontSize: 12, lineHeight: 18, marginBottom: 10 },

  // Sources
  sourceRow: {
    flexDirection: 'row', alignItems: 'flex-start',
    paddingVertical: 10, gap: 10,
    borderBottomWidth: 1, borderBottomColor: C.border,
  },
  sourceMain:      { flex: 1 },
  sourceTitle:     { color: C.text, fontSize: 13, fontWeight: '600' },
  sourceReasoning: { color: C.text3, fontSize: 11, marginTop: 3, lineHeight: 16 },
  sourceLinkBtn:   { padding: 4 },
  sourceLinkBtnText: { color: C.accent, fontSize: 16 },

  // Save / back
  saveBtn: {
    backgroundColor: C.accent, padding: 16,
    borderRadius: 12, alignItems: 'center', marginBottom: 10,
  },
  saveBtnText:    { color: C.bg, fontWeight: '700', fontSize: 15 },
  btnDisabled:    { opacity: 0.5 },
  backBtnBottom:  { alignItems: 'center', padding: 12 },
  backBtnBottomText: { color: C.text3, fontSize: 13 },
});
