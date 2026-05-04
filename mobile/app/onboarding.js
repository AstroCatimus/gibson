/**
 * Gibson — Store Onboarding
 * Shown after signup/login when the user has no store yet.
 *
 * Two paths:
 *   Create — new store, user becomes owner
 *   Join   — enter invite code, immediate employee access
 *
 * After either path, store_id + initials are saved to Supabase
 * user_metadata so getHeaders() picks them up everywhere.
 */

import { useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, Alert,
} from 'react-native';
import { router } from 'expo-router';
import { supabase } from '../src/lib/supabase';

const ACCENT  = '#e94560';
const BG      = '#0f0f1a';
const CARD    = '#13131f';
const BORDER  = '#222';
const MUTED   = '#888';
const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000';

async function apiHeaders() {
  const { data: { session } } = await supabase.auth.getSession();
  return {
    'Content-Type':     'application/json',
    'X-Employee-Id':    session?.user?.id || '',
    'X-Employee-Email': session?.user?.email || '',
    'X-Employee-Name':  session?.user?.user_metadata?.display_name || '',
  };
}

export default function OnboardingScreen() {
  const [step, setStep]           = useState('choose');   // 'choose' | 'create' | 'join' | 'join_confirm'
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');

  // Create fields
  const [storeName, setStoreName] = useState('');
  const [address, setAddress]     = useState('');
  const [prefix, setPrefix]       = useState('');
  const [initials, setInitials]   = useState('');

  // Join fields
  const [code, setCode]           = useState('');
  const [foundStore, setFoundStore] = useState(null);

  // ── Helpers ──────────────────────────────────────────────────

  function reset() {
    setError('');
    setStoreName(''); setAddress(''); setPrefix(''); setInitials('');
    setCode(''); setFoundStore(null);
  }

  async function saveAndEnter(storeId, storeInitials) {
    // Persist store_id + initials into Supabase user metadata
    await supabase.auth.updateUser({
      data: { store_id: storeId, initials: storeInitials || '' },
    });
    router.replace('/(tabs)');
  }

  // ── Create store ─────────────────────────────────────────────

  async function handleCreate() {
    if (!storeName.trim()) { setError('Store name is required.'); return; }
    if (!prefix.trim())    { setError('SKU prefix is required (e.g. DL, MG).'); return; }
    if (prefix.trim().length > 4) { setError('SKU prefix max 4 characters.'); return; }

    setError(''); setLoading(true);
    try {
      const headers = await apiHeaders();
      const resp = await fetch(`${BASE_URL}/api/stores`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          name:    storeName.trim(),
          address: address.trim() || null,
          prefix:  prefix.trim().toUpperCase(),
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      await saveAndEnter(data.store_id, initials.trim().toUpperCase() || prefix.trim().toUpperCase().slice(0, 2));
    } catch (e) {
      setError(e.message || 'Failed to create store.');
    } finally {
      setLoading(false);
    }
  }

  // ── Look up store by code ─────────────────────────────────────

  async function handleLookup() {
    if (!code.trim()) { setError('Enter an invite code.'); return; }
    setError(''); setLoading(true);
    try {
      const headers = await apiHeaders();
      const resp = await fetch(`${BASE_URL}/api/stores/lookup?code=${encodeURIComponent(code.trim().toUpperCase())}`, { headers });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || 'Store not found.');
      if (data.membership?.status === 'active') {
        // Already a member — just enter
        await saveAndEnter(data.store_id, initials.trim().toUpperCase());
        return;
      }
      setFoundStore(data);
      setStep('join_confirm');
    } catch (e) {
      setError(e.message || 'Could not find that store.');
    } finally {
      setLoading(false);
    }
  }

  // ── Join store (immediate via invite code) ────────────────────

  async function handleJoin() {
    if (!foundStore) return;
    setError(''); setLoading(true);
    try {
      const headers = await apiHeaders();
      const resp = await fetch(`${BASE_URL}/api/stores/${foundStore.store_id}/join-direct`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ invite_code: code.trim().toUpperCase() }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      await saveAndEnter(foundStore.store_id, initials.trim().toUpperCase());
    } catch (e) {
      setError(e.message || 'Could not join store.');
    } finally {
      setLoading(false);
    }
  }

  // ── Render ───────────────────────────────────────────────────

  return (
    <KeyboardAvoidingView
      style={s.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">

        <View style={s.header}>
          <Text style={s.wordmark}>Gibson</Text>
          <Text style={s.sub}>Let's set up your store</Text>
        </View>

        {/* ── Choose ───────────────────────────────────────── */}
        {step === 'choose' && (
          <View style={s.choices}>
            <TouchableOpacity style={s.choiceCard} onPress={() => { reset(); setStep('create'); }}>
              <Text style={s.choiceIcon}>🏪</Text>
              <Text style={s.choiceTitle}>Create a Store</Text>
              <Text style={s.choiceSub}>First time setup — you'll be the owner</Text>
            </TouchableOpacity>

            <TouchableOpacity style={s.choiceCard} onPress={() => { reset(); setStep('join'); }}>
              <Text style={s.choiceIcon}>🔑</Text>
              <Text style={s.choiceTitle}>Join a Store</Text>
              <Text style={s.choiceSub}>Enter an invite code from your store owner</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── Create ───────────────────────────────────────── */}
        {step === 'create' && (
          <View style={s.card}>
            <Text style={s.cardTitle}>New Store</Text>

            <Text style={s.label}>Store Name</Text>
            <TextInput style={s.input} value={storeName} onChangeText={setStoreName}
              placeholder="Driftless Books & Music" placeholderTextColor="#444"
              autoCapitalize="words" />

            <Text style={s.label}>Address <Text style={s.optional}>(optional)</Text></Text>
            <TextInput style={s.input} value={address} onChangeText={setAddress}
              placeholder="518 Walnut St, Viroqua WI" placeholderTextColor="#444"
              autoCapitalize="words" />

            <Text style={s.label}>SKU Prefix <Text style={s.optional}>(2–4 letters)</Text></Text>
            <TextInput style={s.input} value={prefix} onChangeText={setPrefix}
              placeholder="DL" placeholderTextColor="#444"
              autoCapitalize="characters" maxLength={4} />
            <Text style={s.hint}>Books get SKUs like {(prefix.toUpperCase() || 'DL')}-1001</Text>

            <Text style={s.label}>Your Initials <Text style={s.optional}>(for SKU attribution)</Text></Text>
            <TextInput style={s.input} value={initials} onChangeText={setInitials}
              placeholder="NM" placeholderTextColor="#444"
              autoCapitalize="characters" maxLength={4} />

            {error ? <Text style={s.error}>{error}</Text> : null}

            <TouchableOpacity style={[s.btn, loading && s.btnOff]} onPress={handleCreate} disabled={loading}>
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnTxt}>Create Store →</Text>}
            </TouchableOpacity>

            <TouchableOpacity onPress={() => { reset(); setStep('choose'); }}>
              <Text style={s.back}>← Back</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── Join: enter code ─────────────────────────────── */}
        {step === 'join' && (
          <View style={s.card}>
            <Text style={s.cardTitle}>Join a Store</Text>

            <Text style={s.label}>Invite Code</Text>
            <TextInput style={[s.input, s.codeInput]} value={code} onChangeText={setCode}
              placeholder="DRIFT1" placeholderTextColor="#444"
              autoCapitalize="characters" maxLength={8} />

            <Text style={s.label}>Your Initials <Text style={s.optional}>(for SKU attribution)</Text></Text>
            <TextInput style={s.input} value={initials} onChangeText={setInitials}
              placeholder="NM" placeholderTextColor="#444"
              autoCapitalize="characters" maxLength={4} />

            {error ? <Text style={s.error}>{error}</Text> : null}

            <TouchableOpacity style={[s.btn, loading && s.btnOff]} onPress={handleLookup} disabled={loading}>
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnTxt}>Look Up Store →</Text>}
            </TouchableOpacity>

            <TouchableOpacity onPress={() => { reset(); setStep('choose'); }}>
              <Text style={s.back}>← Back</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── Join: confirm ────────────────────────────────── */}
        {step === 'join_confirm' && foundStore && (
          <View style={s.card}>
            <Text style={s.cardTitle}>Join this store?</Text>

            <View style={s.storePreview}>
              <Text style={s.storeName}>{foundStore.name}</Text>
              {foundStore.address ? <Text style={s.storeAddr}>{foundStore.address}</Text> : null}
              <Text style={s.storePfx}>SKU prefix: {foundStore.prefix}</Text>
            </View>

            {error ? <Text style={s.error}>{error}</Text> : null}

            <TouchableOpacity style={[s.btn, loading && s.btnOff]} onPress={handleJoin} disabled={loading}>
              {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.btnTxt}>Join {foundStore.name} →</Text>}
            </TouchableOpacity>

            <TouchableOpacity onPress={() => { reset(); setStep('join'); }}>
              <Text style={s.back}>← Use a different code</Text>
            </TouchableOpacity>
          </View>
        )}

      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  root:   { flex: 1, backgroundColor: BG },
  scroll: { flexGrow: 1, padding: 24, paddingBottom: 48 },
  header: { alignItems: 'center', marginBottom: 36, marginTop: 32 },
  wordmark: {
    color: ACCENT, fontSize: 40, fontWeight: '800',
    letterSpacing: -1, fontFamily: 'monospace',
  },
  sub: { color: MUTED, fontSize: 14, marginTop: 6 },

  choices: { gap: 16 },
  choiceCard: {
    backgroundColor: CARD, borderRadius: 16, borderWidth: 1,
    borderColor: BORDER, padding: 24, alignItems: 'center',
  },
  choiceIcon:  { fontSize: 36, marginBottom: 10 },
  choiceTitle: { color: '#fff', fontSize: 18, fontWeight: '700', marginBottom: 4 },
  choiceSub:   { color: MUTED, fontSize: 13, textAlign: 'center' },

  card: {
    backgroundColor: CARD, borderRadius: 16, borderWidth: 1,
    borderColor: BORDER, padding: 20,
  },
  cardTitle: { color: '#fff', fontSize: 18, fontWeight: '700', marginBottom: 16 },

  label:    { color: MUTED, fontSize: 11, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, marginTop: 14 },
  optional: { color: '#555', textTransform: 'none' },
  hint:     { color: '#555', fontSize: 12, marginTop: 4 },
  input: {
    backgroundColor: '#1e1e2e', borderWidth: 1, borderColor: '#333',
    borderRadius: 10, padding: 12, color: '#fff', fontSize: 15,
  },
  codeInput: {
    fontSize: 22, fontWeight: '700', letterSpacing: 4,
    textAlign: 'center', color: ACCENT,
  },

  storePreview: {
    backgroundColor: '#1e1e2e', borderRadius: 12, padding: 16, marginVertical: 12,
  },
  storeName: { color: '#fff', fontSize: 18, fontWeight: '700' },
  storeAddr: { color: MUTED, fontSize: 13, marginTop: 4 },
  storePfx:  { color: '#555', fontSize: 12, marginTop: 6 },

  error: { color: '#e74c3c', fontSize: 13, marginTop: 12 },

  btn: {
    backgroundColor: ACCENT, padding: 16, borderRadius: 12,
    alignItems: 'center', marginTop: 20,
  },
  btnOff:  { opacity: 0.5 },
  btnTxt:  { color: '#fff', fontWeight: '700', fontSize: 16 },
  back: { color: ACCENT, textAlign: 'center', marginTop: 16, fontSize: 14 },
});
