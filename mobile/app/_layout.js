/**
 * Gibson — Root layout.
 * Always renders the Stack (expo-router requires a navigator at the root).
 * Auth redirect happens in a separate effect once the Stack is mounted.
 */

import { useEffect, useState } from 'react';
import { View, ActivityIndicator, StyleSheet } from 'react-native';
import { Stack, router } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { supabase } from '../src/lib/supabase';

const BG    = '#0f0f1a';
const ACCENT = '#e94560';

export default function RootLayout() {
  // undefined = still checking, null = no session, object = has session
  const [session, setSession] = useState(undefined);

  // Step 1: check auth, populate session state
  useEffect(() => {
    let active = true;

    const timeout = setTimeout(() => {
      if (active) setSession(null);
    }, 3000);

    supabase.auth.getSession()
      .then(({ data: { session: s } }) => {
        clearTimeout(timeout);
        if (active) setSession(s ?? null);
      })
      .catch(() => {
        clearTimeout(timeout);
        if (active) setSession(null);
      });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, s) => {
      if (event === 'SIGNED_OUT') setSession(null);
      else if (event === 'SIGNED_IN' && s) setSession(s);
    });

    return () => {
      active = false;
      clearTimeout(timeout);
      subscription.unsubscribe();
    };
  }, []);

  // Step 2: once session is known (Stack is now mounted), navigate
  useEffect(() => {
    if (session === undefined) return; // still loading
    if (!session) {
      router.replace('/login');
      return;
    }
    // Check if user has a store assigned
    const storeId = session.user?.user_metadata?.store_id;
    if (!storeId) {
      router.replace('/onboarding');
    }
    // else: has session + store — stay on tabs (default route)
  }, [session]);

  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: BG } }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="login" />
        <Stack.Screen name="signup" />
        <Stack.Screen name="onboarding" />
        <Stack.Screen
          name="identify"
          options={{
            headerShown: true,
            headerStyle: { backgroundColor: BG },
            headerTintColor: '#fff',
            title: 'Identify',
          }}
        />
        <Stack.Screen
          name="pricing"
          options={{
            headerShown: true,
            headerStyle: { backgroundColor: BG },
            headerTintColor: '#fff',
            title: 'Pricing',
          }}
        />
        <Stack.Screen
          name="condition"
          options={{
            headerShown: true,
            headerStyle: { backgroundColor: BG },
            headerTintColor: '#fff',
            title: 'Condition',
          }}
        />
        <Stack.Screen
          name="catalogue"
          options={{
            headerShown: true,
            headerStyle: { backgroundColor: BG },
            headerTintColor: '#fff',
            title: 'Confirm & Add',
          }}
        />
      </Stack>

      {/* Loading veil — sits on top of the Stack while auth is checking */}
      {session === undefined && (
        <View style={styles.veil}>
          <ActivityIndicator color={ACCENT} size="large" />
        </View>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  veil: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: BG,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
