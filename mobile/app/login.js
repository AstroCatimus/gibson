/**
 * Gibson — Login screen.
 */

import { useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { router } from 'expo-router';
import { supabase } from '../src/lib/supabase';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const CARD = '#13131f';

export default function LoginScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleLogin() {
    if (!email.trim() || !password) {
      setError('Email and password are required.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
      if (error) throw error;
      // onAuthStateChange in _layout.js handles the redirect
    } catch (e) {
      setError(e.message || 'Login failed.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={s.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <View style={s.header}>
          <Text style={s.wordmark}>Gibson</Text>
          <Text style={s.sub}>Alexandria Book Co-op</Text>
        </View>

        <View style={s.card}>
          <Text style={s.label}>Email</Text>
          <TextInput
            style={s.input}
            value={email}
            onChangeText={setEmail}
            placeholder="you@example.com"
            placeholderTextColor="#444"
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
          />

          <Text style={s.label}>Password</Text>
          <TextInput
            style={s.input}
            value={password}
            onChangeText={setPassword}
            placeholder="••••••••"
            placeholderTextColor="#444"
            secureTextEntry
          />

          {error ? <Text style={s.error}>{error}</Text> : null}

          <TouchableOpacity
            style={[s.btn, loading && s.btnDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading
              ? <ActivityIndicator color="#fff" />
              : <Text style={s.btnText}>Sign In</Text>
            }
          </TouchableOpacity>
        </View>

        <TouchableOpacity onPress={() => router.push('/signup')}>
          <Text style={s.switchText}>
            No account? <Text style={s.switchLink}>Create one</Text>
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  scroll: { flexGrow: 1, justifyContent: 'center', padding: 24 },
  header: { alignItems: 'center', marginBottom: 40 },
  wordmark: {
    color: ACCENT, fontSize: 42, fontWeight: '800',
    letterSpacing: -1, fontFamily: 'monospace',
  },
  sub: { color: '#555', fontSize: 13, marginTop: 4, letterSpacing: 1 },
  card: {
    backgroundColor: CARD, borderRadius: 16, padding: 20,
    borderWidth: 1, borderColor: '#222', marginBottom: 20,
  },
  label: { color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, marginTop: 14 },
  input: {
    backgroundColor: '#1e1e2e', borderWidth: 1, borderColor: '#333',
    borderRadius: 10, padding: 12, color: '#fff', fontSize: 15,
  },
  error: { color: '#e74c3c', fontSize: 13, marginTop: 12 },
  btn: {
    backgroundColor: ACCENT, padding: 16, borderRadius: 12,
    alignItems: 'center', marginTop: 20,
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  switchText: { color: '#555', textAlign: 'center', fontSize: 14 },
  switchLink: { color: ACCENT, fontWeight: '600' },
});
