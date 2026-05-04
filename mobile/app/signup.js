/**
 * Gibson — Account creation screen.
 * Name, email, password only. Store is assigned later via Settings.
 */

import { useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { router } from 'expo-router';
import { supabase } from '../src/lib/supabase';

const ACCENT = '#e94560';
const BG     = '#0f0f1a';
const CARD   = '#13131f';

export default function SignupScreen() {
  const [name, setName]         = useState('');
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm]   = useState('');
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  async function handleSignup() {
    if (!name.trim() || !email.trim() || !password) {
      setError('All fields are required.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    setError('');
    setLoading(true);
    try {
      const { error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: { data: { display_name: name.trim() } },
      });
      if (error) throw error;
      // Auth listener in _layout.js handles redirect on session
    } catch (e) {
      setError(e.message || 'Signup failed.');
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
          <Text style={s.sub}>Create your account</Text>
        </View>

        <View style={s.card}>
          <Text style={s.label}>Your Name</Text>
          <TextInput
            style={s.input}
            value={name}
            onChangeText={setName}
            placeholder="First Last"
            placeholderTextColor="#444"
            autoCapitalize="words"
          />

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
            placeholder="At least 8 characters"
            placeholderTextColor="#444"
            secureTextEntry
          />

          <Text style={s.label}>Confirm Password</Text>
          <TextInput
            style={s.input}
            value={confirm}
            onChangeText={setConfirm}
            placeholder="••••••••"
            placeholderTextColor="#444"
            secureTextEntry
          />
        </View>

        {error ? <Text style={s.error}>{error}</Text> : null}

        <TouchableOpacity
          style={[s.btn, loading && s.btnDisabled]}
          onPress={handleSignup}
          disabled={loading}
        >
          {loading
            ? <ActivityIndicator color="#fff" />
            : <Text style={s.btnText}>Create Account</Text>
          }
        </TouchableOpacity>

        <Text style={s.hint}>
          You can join or create a store from Settings after signing in.
        </Text>

        <TouchableOpacity onPress={() => router.back()}>
          <Text style={s.switchText}>
            Already have an account? <Text style={s.switchLink}>Sign in</Text>
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  scroll: { flexGrow: 1, padding: 24, paddingBottom: 40 },
  header: { alignItems: 'center', marginBottom: 32, marginTop: 20 },
  wordmark: {
    color: ACCENT, fontSize: 36, fontWeight: '800',
    letterSpacing: -1, fontFamily: 'monospace',
  },
  sub: { color: '#555', fontSize: 13, marginTop: 4 },
  card: {
    backgroundColor: CARD, borderRadius: 16, padding: 20,
    borderWidth: 1, borderColor: '#222', marginBottom: 20,
  },
  label: {
    color: '#888', fontSize: 12, textTransform: 'uppercase',
    letterSpacing: 1, marginBottom: 6, marginTop: 14,
  },
  input: {
    backgroundColor: '#1e1e2e', borderWidth: 1, borderColor: '#333',
    borderRadius: 10, padding: 12, color: '#fff', fontSize: 15,
  },
  error: { color: '#e74c3c', fontSize: 13, marginTop: 4, marginBottom: 4 },
  hint: { color: '#444', fontSize: 12, textAlign: 'center', marginTop: 8, marginBottom: 16 },
  btn: {
    backgroundColor: ACCENT, padding: 16, borderRadius: 12,
    alignItems: 'center', marginTop: 4, marginBottom: 12,
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  switchText: { color: '#555', textAlign: 'center', fontSize: 14, marginBottom: 20 },
  switchLink: { color: ACCENT, fontWeight: '600' },
});
