/**
 * Gibson — Identify Result Screen.
 * Shows what Gibson found with per-field confidence bars.
 * One tap to confirm, or edit any field before cataloguing.
 */

import { useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  TextInput, ActivityIndicator, Image,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';

import { C } from '../src/lib/theme';

const ACCENT  = C.accent;
const BG      = C.bg;
const CARD    = C.card;
const GREEN   = C.green;
const YELLOW  = C.yellow;
const RED     = C.red;

function confColor(pct) {
  return pct >= 85 ? GREEN : pct >= 60 ? YELLOW : RED;
}

function ConfidencePill({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = confColor(pct);
  const label = pct >= 85 ? 'High' : pct >= 60 ? 'Medium' : 'Low';
  return (
    <View style={[s.confPill, { borderColor: color, backgroundColor: color + '18' }]}>
      <View style={[s.confDot, { backgroundColor: color }]} />
      <Text style={[s.confPillText, { color }]}>{pct}% · {label} confidence</Text>
    </View>
  );
}

function ConfidenceBar({ value, label }) {
  const pct = Math.round((value || 0) * 100);
  const color = confColor(pct);
  return (
    <View style={s.confRow}>
      <Text style={s.confLabel}>{label}</Text>
      <View style={s.confTrack}>
        <View style={[s.confFill, { width: `${pct}%`, backgroundColor: color }]} />
      </View>
      <Text style={[s.confPct, { color }]}>{pct}%</Text>
    </View>
  );
}

export default function IdentifyScreen() {
  const params = useLocalSearchParams();
  const result   = params.result   ? JSON.parse(params.result) : null;
  const coverUri = params.coverUri || result?.cover_image_url || null;

  const [title,     setTitle]     = useState(result?.title || '');
  const [author,    setAuthor]    = useState(result?.author || '');
  const [publisher, setPublisher] = useState(result?.publisher || '');
  const [isbn,      setIsbn]      = useState(result?.isbn_13 || '');
  const [year,      setYear]      = useState(String(result?.publication_year || ''));
  const [loading, setLoading] = useState(false);

  if (!result) {
    return (
      <View style={s.errorScreen}>
        <Text style={s.errorIcon}>⚠️</Text>
        <Text style={s.errorText}>No identification result.</Text>
        <TouchableOpacity style={s.backLink} onPress={() => router.back()}>
          <Text style={s.backLinkText}>← Go back</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const path = result.path?.replace(/_/g, ' ') || 'standard path';

  function handleConfirm() {
    router.push({
      pathname: '/pricing',
      params: { isbn, title, author, publisher, year, editionId: result.edition_id || '' },
    });
  }

  function handleDeepLookup() {
    router.push({
      pathname: '/deep_lookup',
      params: { title, author, publisher, year, isbn,
                stockItemId: result.edition_id || '' },
    });
  }

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* Cover image */}
      {coverUri ? (
        <Image source={{ uri: coverUri }} style={s.coverImage} resizeMode="contain" />
      ) : null}

      {/* No cover found — ask user to photograph it */}
      {result?.needs_cover_photo && (
        <View style={s.coverPromptCard}>
          <Text style={s.coverPromptIcon}>📷</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.coverPromptTitle}>No cover image on file</Text>
            <Text style={s.coverPromptText}>
              Take a photo of the cover and we'll save it to the database for future scans.
            </Text>
          </View>
        </View>
      )}

      {/* Confidence hero */}
      <View style={s.card}>
        <Text style={s.cardLabel}>Gibson's Read</Text>
        <ConfidencePill value={result.confidence} />
        <Text style={s.pathLabel}>{path}</Text>
      </View>

      {/* Editable fields */}
      <View style={s.card}>
        <Text style={s.cardLabel}>Bibliographic Details</Text>

        <Text style={s.fieldLabel}>Title</Text>
        <TextInput
          style={s.input}
          value={title}
          onChangeText={setTitle}
          placeholderTextColor="#444"
          placeholder="Book title"
        />

        <Text style={s.fieldLabel}>Author</Text>
        <TextInput
          style={s.input}
          value={author}
          onChangeText={setAuthor}
          placeholderTextColor="#444"
          placeholder="Author name"
        />

        <Text style={s.fieldLabel}>Publisher</Text>
        <TextInput
          style={s.input}
          value={publisher}
          onChangeText={setPublisher}
          placeholderTextColor="#444"
          placeholder="Publisher"
        />

        <View style={s.fieldRow}>
          <View style={{ flex: 2 }}>
            <Text style={s.fieldLabel}>ISBN-13</Text>
            <TextInput
              style={s.input}
              value={isbn}
              onChangeText={setIsbn}
              keyboardType="numeric"
              placeholderTextColor="#444"
              placeholder="978…"
            />
          </View>
          <View style={{ width: 12 }} />
          <View style={{ flex: 1 }}>
            <Text style={s.fieldLabel}>Year</Text>
            <TextInput
              style={s.input}
              value={year}
              onChangeText={setYear}
              keyboardType="numeric"
              maxLength={4}
              placeholderTextColor="#444"
              placeholder="1984"
            />
          </View>
        </View>
      </View>

      {/* Per-field confidence */}
      {result.per_field_confidence && Object.keys(result.per_field_confidence).length > 0 && (
        <View style={s.card}>
          <Text style={s.cardLabel}>Field Confidence</Text>
          {Object.entries(result.per_field_confidence).map(([field, val]) => (
            <ConfidenceBar key={field} label={field} value={val} />
          ))}
        </View>
      )}

      {/* Follow-up request */}
      {result.follow_up_request && (
        <View style={[s.card, s.followUpCard]}>
          <Text style={s.followUpIcon}>💬</Text>
          <Text style={s.followUpText}>{result.follow_up_request}</Text>
          <TouchableOpacity
            style={s.followUpBtn}
            onPress={() => router.push('/')}
          >
            <Text style={s.followUpBtnText}>Take Another Photo</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Deep lookup */}
      <TouchableOpacity style={s.deepLookupSmall} onPress={handleDeepLookup}>
        <Text style={s.deepLookupSmallText}>🔍  Deep lookup</Text>
      </TouchableOpacity>

      {/* CTA */}
      <TouchableOpacity
        style={[s.primaryBtn, loading && s.btnDisabled]}
        onPress={handleConfirm}
        disabled={loading}
      >
        {loading
          ? <ActivityIndicator color="#fff" />
          : <Text style={s.primaryBtnText}>Get Pricing →</Text>
        }
      </TouchableOpacity>

      <TouchableOpacity style={s.ghostBtn} onPress={() => router.back()}>
        <Text style={s.ghostBtnText}>Rescan</Text>
      </TouchableOpacity>

    </ScrollView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  content: { padding: 16, paddingBottom: 40 },

  coverImage: {
    width: '100%', height: 220, borderRadius: 10,
    marginBottom: 12, backgroundColor: '#0c0c17',
  },
  coverPromptCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: '#1a1a10', borderWidth: 1, borderColor: '#3a3a10',
    borderRadius: 10, padding: 12, marginBottom: 12,
  },
  coverPromptIcon: { fontSize: 24 },
  coverPromptTitle: { color: '#f0d060', fontSize: 13, fontWeight: '700', marginBottom: 2 },
  coverPromptText: { color: '#888', fontSize: 12, lineHeight: 16 },

  errorScreen: { flex: 1, backgroundColor: BG, alignItems: 'center', justifyContent: 'center' },
  errorIcon: { fontSize: 48, marginBottom: 12 },
  errorText: { color: '#888', fontSize: 16 },
  backLink: { marginTop: 16 },
  backLinkText: { color: ACCENT, fontSize: 14 },

  card: {
    backgroundColor: CARD,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1e1e2e',
  },
  cardLabel: {
    color: '#444',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 12,
  },

  confPill: {
    flexDirection: 'row', alignItems: 'center',
    borderWidth: 1, borderRadius: 20,
    paddingHorizontal: 12, paddingVertical: 7,
    gap: 8, alignSelf: 'flex-start',
  },
  confDot: { width: 7, height: 7, borderRadius: 4 },
  confPillText: { fontSize: 14, fontWeight: '700' },
  pathLabel: { color: '#444', fontSize: 12, marginTop: 8, textTransform: 'capitalize' },

  fieldLabel: { color: '#555', fontSize: 12, marginBottom: 4, marginTop: 12 },
  fieldRow: { flexDirection: 'row', marginTop: 0 },
  input: {
    backgroundColor: '#1a1a2a',
    borderWidth: 1,
    borderColor: '#252535',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: '#fff',
    fontSize: 14,
  },

  confRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 9, gap: 8 },
  confLabel: { color: '#666', fontSize: 12, width: 80, textTransform: 'capitalize' },
  confTrack: {
    flex: 1, height: 5,
    backgroundColor: '#1a1a2a', borderRadius: 3, overflow: 'hidden',
  },
  confFill: { height: '100%', borderRadius: 3 },
  confPct: { fontSize: 11, width: 34, textAlign: 'right', fontWeight: '600' },

  followUpCard: { borderColor: YELLOW + '88' },
  followUpIcon: { fontSize: 24, marginBottom: 8 },
  followUpText: { color: '#ddd', fontSize: 14, lineHeight: 20, marginBottom: 12 },
  followUpBtn: {
    backgroundColor: YELLOW + '22',
    borderWidth: 1, borderColor: YELLOW,
    borderRadius: 8, padding: 10, alignItems: 'center',
  },
  followUpBtnText: { color: YELLOW, fontWeight: '700', fontSize: 13 },

  // Deep lookup link
  deepLookupSmall: { alignItems: 'center', paddingVertical: 6, marginBottom: 6 },
  deepLookupSmallText: { color: C.text3, fontSize: 12 },

  primaryBtn: {
    backgroundColor: ACCENT, padding: 16,
    borderRadius: 12, alignItems: 'center', marginBottom: 10,
  },
  primaryBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  btnDisabled: { opacity: 0.5 },

  ghostBtn: { alignItems: 'center', padding: 12 },
  ghostBtnText: { color: '#444', fontSize: 14 },
});
