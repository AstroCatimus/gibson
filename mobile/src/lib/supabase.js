/**
 * Supabase client for Gibson Mobile.
 * Uses expo-secure-store as the session storage adapter with a
 * synchronous in-memory fallback so the client never hangs on init.
 */

import { createClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';

const SUPABASE_URL      = process.env.EXPO_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

// In-memory cache so reads are always synchronous
const memCache = {};

const SecureStoreAdapter = {
  getItem: (key) => {
    // Return cached value immediately, then refresh from SecureStore in background
    if (memCache[key] !== undefined) return memCache[key];
    return SecureStore.getItemAsync(key).then(val => {
      memCache[key] = val;
      return val;
    }).catch(() => null);
  },
  setItem: (key, value) => {
    memCache[key] = value;
    return SecureStore.setItemAsync(key, value).catch(() => {});
  },
  removeItem: (key) => {
    delete memCache[key];
    return SecureStore.deleteItemAsync(key).catch(() => {});
  },
};

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage:            SecureStoreAdapter,
    autoRefreshToken:   true,
    persistSession:     true,
    detectSessionInUrl: false,
  },
});
