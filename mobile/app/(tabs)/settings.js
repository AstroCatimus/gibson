/**
 * Gibson — Account & Settings Screen.
 * Account info, store management (join / create / approve members), sign out.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Alert,
  ScrollView, ActivityIndicator, TextInput, Modal, FlatList,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../src/lib/api';
import { supabase } from '../../src/lib/supabase';
import { logger } from '../../src/lib/logger';
import { C } from '../../src/lib/theme';

// ─── Small helpers ────────────────────────────────────────────────

function SectionLabel({ children }) {
  return <Text style={s.sectionLabel}>{children}</Text>;
}

function Divider() {
  return <View style={s.divider} />;
}

// ─── Main screen ─────────────────────────────────────────────────

export default function SettingsScreen() {
  const [user, setUser]                   = useState(null);
  const [myStores, setMyStores]           = useState([]);
  const [activeStoreId, setActiveStoreId] = useState('');
  const [loadingStores, setLoadingStores] = useState(true);
  const [apiStatus, setApiStatus]         = useState(null);
  const [checking, setChecking]           = useState(false);

  const [showJoin, setShowJoin]         = useState(false);
  const [showCreate, setShowCreate]     = useState(false);
  const [showRequests, setShowRequests] = useState(null);
  const [showLogs, setShowLogs]         = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        setUser(session.user);
        const meta = session.user.user_metadata || {};
        setActiveStoreId(meta.store_id || '');
      }
    });
    loadStores();
    checkApi();
  }, []);

  const loadStores = useCallback(async () => {
    setLoadingStores(true);
    try {
      const { stores } = await api.getMyStores();
      setMyStores(stores || []);
    } catch {
      setMyStores([]);
    } finally {
      setLoadingStores(false);
    }
  }, []);

  async function checkApi() {
    setChecking(true);
    try {
      await api.health();
      setApiStatus('ok');
    } catch {
      setApiStatus('error');
    } finally {
      setChecking(false);
    }
  }

  async function switchStore(id) {
    setActiveStoreId(id);
    await supabase.auth.updateUser({ data: { store_id: id } });
  }

  async function handleSignOut() {
    Alert.alert('Sign Out', 'Sign out of Gibson?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign Out', style: 'destructive', onPress: () => supabase.auth.signOut() },
    ]);
  }

  const meta        = user?.user_metadata || {};
  const displayName = meta.display_name || user?.email?.split('@')[0] || '';
  const initials    = displayName
    ? displayName.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
    : '?';

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* ── Account card ── */}
      <View style={s.card}>
        <View style={s.accountRow}>
          <View style={s.avatar}>
            <Text style={s.avatarText}>{initials}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.accountName}>{displayName || 'Gibson User'}</Text>
            <Text style={s.accountEmail}>{user?.email || ''}</Text>
          </View>
        </View>
        <Divider />
        <TouchableOpacity style={s.signOutRow} onPress={handleSignOut}>
          <Ionicons name="log-out-outline" size={18} color={C.red} />
          <Text style={s.signOutText}>Sign Out</Text>
        </TouchableOpacity>
      </View>

      {/* ── Stores ── */}
      <SectionLabel>Your Stores</SectionLabel>
      <View style={s.card}>
        {loadingStores ? (
          <ActivityIndicator color={C.accent} style={{ margin: 20 }} />
        ) : myStores.length === 0 ? (
          <View style={s.emptyStores}>
            <Text style={s.emptyStoresText}>You haven't joined any stores yet.</Text>
          </View>
        ) : (
          myStores.map((store, idx) => {
            const active  = activeStoreId === store.store_id;
            const isAdmin = ['owner', 'admin'].includes(store.role);
            const pending = parseInt(store.pending_requests || 0, 10);
            return (
              <View key={store.store_id}>
                {idx > 0 && <Divider />}
                <TouchableOpacity
                  style={[s.storeRow, active && s.storeRowActive]}
                  onPress={() => switchStore(store.store_id)}
                  activeOpacity={0.7}
                >
                  <View style={[s.storePrefix, active && s.storePrefixActive]}>
                    <Text style={[s.storePrefixText, active && s.storePrefixTextActive]}>
                      {store.prefix}
                    </Text>
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={[s.storeName, active && s.storeNameActive]} numberOfLines={1} ellipsizeMode="tail">
                      {store.name}
                    </Text>
                    <View style={s.storeMetaRow}>
                      <View style={s.roleBadge}>
                        <Text style={s.roleBadgeText}>{store.role}</Text>
                      </View>
                      {store.address ? (
                        <Text style={s.storeAddr}>{store.address}</Text>
                      ) : null}
                    </View>
                  </View>
                  <View style={s.storeRight}>
                    {active && <Ionicons name="checkmark-circle" size={20} color={C.accent} />}
                    {isAdmin && pending > 0 && (
                      <TouchableOpacity
                        style={s.pendingBadge}
                        onPress={() => setShowRequests(store.store_id)}
                      >
                        <Text style={s.pendingBadgeText}>{pending}</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </TouchableOpacity>

                {isAdmin && store.invite_code && (
                  <View style={s.inviteRow}>
                    <Ionicons name="key-outline" size={13} color={C.text3} />
                    <Text style={s.inviteLabel}>Invite code</Text>
                    <Text style={s.inviteCode}>{store.invite_code}</Text>
                    {isAdmin && pending > 0 && (
                      <TouchableOpacity style={{ marginLeft: 'auto' }} onPress={() => setShowRequests(store.store_id)}>
                        <Text style={s.reviewBtnText}>{pending} pending →</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                )}
              </View>
            );
          })
        )}
      </View>

      {/* ── Find a store ── */}
      <SectionLabel>Find a Store</SectionLabel>
      <View style={s.card}>
        <TouchableOpacity style={s.actionRow} onPress={() => setShowJoin(true)}>
          <View style={s.actionIcon}>
            <Ionicons name="key-outline" size={18} color={C.accent} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.actionTitle}>Join with Invite Code</Text>
            <Text style={s.actionHint}>Enter the code from your store owner</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={C.text3} />
        </TouchableOpacity>
        <Divider />
        <TouchableOpacity style={s.actionRow} onPress={() => setShowCreate(true)}>
          <View style={s.actionIcon}>
            <Ionicons name="storefront-outline" size={18} color={C.accent} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.actionTitle}>Create a Store</Text>
            <Text style={s.actionHint}>Start a new store — you'll be the owner</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={C.text3} />
        </TouchableOpacity>
      </View>

      {/* ── Connection ── */}
      <SectionLabel>Connection</SectionLabel>
      <View style={s.card}>
        <View style={s.statusRow}>
          <View style={{ flex: 1 }}>
            <Text style={s.statusLabel}>API Server</Text>
            <Text style={s.apiUrl}>{process.env.EXPO_PUBLIC_API_BASE_URL}</Text>
          </View>
          {checking
            ? <ActivityIndicator color={C.accent} size="small" />
            : (
              <View style={[s.statusBadge, {
                borderColor: apiStatus === 'ok' ? C.green : C.red,
              }]}>
                <View style={[s.statusDot, {
                  backgroundColor: apiStatus === 'ok' ? C.green : C.red,
                }]} />
                <Text style={[s.statusText, {
                  color: apiStatus === 'ok' ? C.green : C.red,
                }]}>
                  {apiStatus === 'ok' ? 'Online' : 'Offline'}
                </Text>
              </View>
            )
          }
        </View>
        <Divider />
        <TouchableOpacity onPress={checkApi} style={s.retryRow}>
          <Ionicons name="refresh-outline" size={14} color={C.text2} />
          <Text style={s.retryText}>Check Again</Text>
        </TouchableOpacity>
      </View>

      {/* ── Developer ── */}
      <SectionLabel>Developer</SectionLabel>
      <View style={s.card}>
        <TouchableOpacity style={s.actionRow} onPress={() => setShowLogs(true)}>
          <View style={s.actionIcon}>
            <Ionicons name="terminal-outline" size={18} color={C.accent} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.actionTitle}>Debug Logs</Text>
            <Text style={s.actionHint}>API calls, errors, auth events</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={C.text3} />
        </TouchableOpacity>
      </View>

      <Text style={s.version}>Gibson v1.0 · Alexandria Book Co-op · Viroqua, WI</Text>

      {/* ── Modals ── */}
      <JoinModal
        visible={showJoin}
        onClose={() => setShowJoin(false)}
        onSuccess={() => { setShowJoin(false); loadStores(); }}
      />
      <CreateModal
        visible={showCreate}
        onClose={() => setShowCreate(false)}
        onSuccess={(newStore) => { setShowCreate(false); loadStores(); switchStore(newStore.store_id); }}
      />
      <LogsModal visible={showLogs} onClose={() => setShowLogs(false)} />
      {showRequests && (
        <RequestsModal
          storeId={showRequests}
          storeName={myStores.find(st => st.store_id === showRequests)?.name || ''}
          onClose={() => { setShowRequests(null); loadStores(); }}
        />
      )}
    </ScrollView>
  );
}

// ─── Join Store Modal ─────────────────────────────────────────────

function JoinModal({ visible, onClose, onSuccess }) {
  const [code, setCode]       = useState('');
  const [message, setMessage] = useState('');
  const [found, setFound]     = useState(null);
  const [step, setStep]       = useState('code');
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');

  function reset() { setCode(''); setMessage(''); setFound(null); setStep('code'); setError(''); }

  async function handleLookup() {
    if (code.trim().length < 4) { setError('Enter the full invite code.'); return; }
    setLoading(true); setError('');
    try {
      const result = await api.lookupStoreByCode(code.trim());
      if (result.membership?.status === 'active') { setError("You're already a member of this store."); return; }
      if (result.join_request?.status === 'pending') { setError('You already have a pending request.'); return; }
      setFound(result);
      setStep('confirm');
    } catch (e) {
      setError(e.message || 'Store not found. Check the code and try again.');
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit() {
    setLoading(true); setError('');
    try {
      await api.requestToJoin(found.store_id, code.trim(), message.trim() || null);
      setStep('sent');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={m.container}>
        <View style={m.header}>
          <Text style={m.title}>Join a Store</Text>
          <TouchableOpacity onPress={() => { reset(); onClose(); }}>
            <Ionicons name="close" size={24} color={C.text2} />
          </TouchableOpacity>
        </View>

        {step === 'code' && (
          <>
            <Text style={m.label}>Invite Code</Text>
            <TextInput
              style={m.input}
              value={code}
              onChangeText={t => { setCode(t.toUpperCase()); setError(''); }}
              placeholder="e.g. DRIFT1"
              placeholderTextColor={C.text3}
              autoCapitalize="characters"
              maxLength={8}
            />
            {error ? <Text style={m.error}>{error}</Text> : null}
            <TouchableOpacity
              style={[m.btn, (!code.trim() || loading) && m.btnDisabled]}
              onPress={handleLookup}
              disabled={!code.trim() || loading}
            >
              {loading ? <ActivityIndicator color={C.bg} /> : <Text style={m.btnText}>Find Store</Text>}
            </TouchableOpacity>
          </>
        )}

        {step === 'confirm' && found && (
          <>
            <View style={m.storePreview}>
              <Text style={m.previewPrefix}>{found.prefix}</Text>
              <View>
                <Text style={m.previewName}>{found.name}</Text>
                {found.address && <Text style={m.previewAddr}>{found.address}</Text>}
              </View>
            </View>

            <Text style={m.label}>Message <Text style={m.optional}>(optional)</Text></Text>
            <TextInput
              style={[m.input, { height: 80, textAlignVertical: 'top' }]}
              value={message}
              onChangeText={setMessage}
              placeholder="Hi, I'm a new employee…"
              placeholderTextColor={C.text3}
              multiline
            />
            {error ? <Text style={m.error}>{error}</Text> : null}
            <Text style={m.hint}>Your request will be sent to the store owner for approval.</Text>
            <TouchableOpacity
              style={[m.btn, loading && m.btnDisabled]}
              onPress={handleSubmit}
              disabled={loading}
            >
              {loading ? <ActivityIndicator color={C.bg} /> : <Text style={m.btnText}>Send Join Request</Text>}
            </TouchableOpacity>
            <TouchableOpacity style={m.ghostBtn} onPress={() => setStep('code')}>
              <Text style={m.ghostBtnText}>← Back</Text>
            </TouchableOpacity>
          </>
        )}

        {step === 'sent' && (
          <View style={m.successWrap}>
            <Ionicons name="mail-outline" size={56} color={C.accent} style={{ marginBottom: 16 }} />
            <Text style={m.successTitle}>Request Sent</Text>
            <Text style={m.successText}>
              The store owner will review your request. Check back in Account once they've responded.
            </Text>
            <TouchableOpacity style={m.btn} onPress={() => { reset(); onSuccess(); }}>
              <Text style={m.btnText}>Done</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    </Modal>
  );
}

// ─── Create Store Modal ───────────────────────────────────────────

function CreateModal({ visible, onClose, onSuccess }) {
  const [name, setName]       = useState('');
  const [address, setAddress] = useState('');
  const [prefix, setPrefix]   = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');

  function reset() { setName(''); setAddress(''); setPrefix(''); setError(''); }

  async function handleCreate() {
    if (!name.trim())   { setError('Store name is required.'); return; }
    if (!prefix.trim()) { setError('SKU prefix is required (e.g. DL, MG).'); return; }
    if (!/^[A-Za-z]{1,4}$/.test(prefix.trim())) { setError('Prefix must be 1–4 letters only.'); return; }
    setLoading(true); setError('');
    try {
      const result = await api.createStore({
        name:    name.trim(),
        address: address.trim() || null,
        prefix:  prefix.trim().toUpperCase(),
      });
      reset();
      onSuccess(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={m.container}>
        <View style={m.header}>
          <Text style={m.title}>Create a Store</Text>
          <TouchableOpacity onPress={() => { reset(); onClose(); }}>
            <Ionicons name="close" size={24} color={C.text2} />
          </TouchableOpacity>
        </View>

        <Text style={m.label}>Store Name</Text>
        <TextInput style={m.input} value={name} onChangeText={setName}
          placeholder="Driftless Books & Music" placeholderTextColor={C.text3} />

        <Text style={m.label}>Address <Text style={m.optional}>(optional)</Text></Text>
        <TextInput style={m.input} value={address} onChangeText={setAddress}
          placeholder="518 Walnut St, Viroqua WI" placeholderTextColor={C.text3} />

        <Text style={m.label}>SKU Prefix</Text>
        <TextInput style={m.input} value={prefix}
          onChangeText={t => setPrefix(t.toUpperCase())}
          placeholder="DL" placeholderTextColor={C.text3}
          autoCapitalize="characters" maxLength={4} />
        <Text style={m.hint}>2–4 letters that start every SKU (e.g. DL-1234). Must be unique.</Text>

        {error ? <Text style={m.error}>{error}</Text> : null}

        <TouchableOpacity
          style={[m.btn, (!name.trim() || !prefix.trim() || loading) && m.btnDisabled]}
          onPress={handleCreate}
          disabled={!name.trim() || !prefix.trim() || loading}
        >
          {loading ? <ActivityIndicator color={C.bg} /> : <Text style={m.btnText}>Create Store</Text>}
        </TouchableOpacity>
        <TouchableOpacity style={m.ghostBtn} onPress={() => { reset(); onClose(); }}>
          <Text style={m.ghostBtnText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    </Modal>
  );
}

// ─── Pending Requests Modal ───────────────────────────────────────

function RequestsModal({ storeId, storeName, onClose }) {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [acting, setActing]     = useState(null);

  useEffect(() => { loadRequests(); }, []);

  async function loadRequests() {
    setLoading(true);
    try {
      const { requests: reqs } = await api.getJoinRequests(storeId);
      setRequests(reqs || []);
    } catch { setRequests([]); }
    finally { setLoading(false); }
  }

  async function handle(requestId, action) {
    setActing(requestId);
    try {
      await api.reviewJoinRequest(storeId, requestId, action);
      setRequests(prev => prev.filter(r => r.request_id !== requestId));
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setActing(null);
    }
  }

  return (
    <Modal visible animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={m.container}>
        <View style={m.header}>
          <Text style={m.title}>Join Requests</Text>
          <TouchableOpacity onPress={onClose}>
            <Ionicons name="close" size={24} color={C.text2} />
          </TouchableOpacity>
        </View>
        <Text style={m.storeSubtitle}>{storeName}</Text>

        {loading ? (
          <ActivityIndicator color={C.accent} style={{ marginTop: 40 }} />
        ) : requests.length === 0 ? (
          <View style={m.emptyWrap}>
            <Ionicons name="checkmark-circle" size={48} color={C.green} style={{ marginBottom: 12 }} />
            <Text style={m.emptyText}>No pending requests</Text>
          </View>
        ) : (
          <ScrollView style={{ flex: 1 }}>
            {requests.map(req => (
              <View key={req.request_id} style={m.requestCard}>
                <View style={m.requestInfo}>
                  <Text style={m.requestName}>{req.user_name || 'Unknown'}</Text>
                  <Text style={m.requestEmail}>{req.user_email}</Text>
                  {req.message && (
                    <Text style={m.requestMessage}>"{req.message}"</Text>
                  )}
                  <Text style={m.requestDate}>{new Date(req.created_at).toLocaleDateString()}</Text>
                </View>
                <View style={m.requestActions}>
                  {acting === req.request_id ? (
                    <ActivityIndicator color={C.accent} />
                  ) : (
                    <>
                      <TouchableOpacity style={m.approveBtn} onPress={() => handle(req.request_id, 'approve')}>
                        <Text style={m.approveBtnText}>Approve</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={m.denyBtn} onPress={() => handle(req.request_id, 'deny')}>
                        <Text style={m.denyBtnText}>Deny</Text>
                      </TouchableOpacity>
                    </>
                  )}
                </View>
              </View>
            ))}
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

// ─── Logs Modal ───────────────────────────────────────────────────

const LOG_COLORS = {
  error: C.red,
  warn:  C.yellow,
  info:  C.blue,
  debug: C.text3,
};

function LogsModal({ visible, onClose }) {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    if (!visible) return;
    const unsub = logger.subscribe(setLogs);
    return unsub;
  }, [visible]);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={lm.container}>
        <View style={lm.header}>
          <Text style={lm.title}>Debug Logs</Text>
          <View style={lm.headerRight}>
            <TouchableOpacity onPress={() => logger.clear()} style={lm.clearBtn}>
              <Text style={lm.clearBtnText}>Clear</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={C.text2} />
            </TouchableOpacity>
          </View>
        </View>

        {logs.length === 0 ? (
          <View style={lm.empty}>
            <Text style={lm.emptyText}>No logs yet. Try an API call.</Text>
          </View>
        ) : (
          <FlatList
            data={logs}
            keyExtractor={item => String(item.id)}
            style={{ flex: 1 }}
            contentContainerStyle={{ padding: 12 }}
            renderItem={({ item }) => (
              <View style={lm.entry}>
                <View style={lm.entryHeader}>
                  <Text style={[lm.level, { color: LOG_COLORS[item.level] }]}>
                    {item.level.toUpperCase()}
                  </Text>
                  <Text style={lm.time}>{new Date(item.timestamp).toLocaleTimeString()}</Text>
                </View>
                <Text style={lm.message}>{item.message}</Text>
                {item.data ? (
                  <Text style={lm.data} numberOfLines={4}>{item.data}</Text>
                ) : null}
              </View>
            )}
          />
        )}
      </View>
    </Modal>
  );
}

// ─── Log modal styles ─────────────────────────────────────────────
const lm = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', padding: 16,
    borderBottomWidth: 1, borderBottomColor: C.border,
    backgroundColor: C.surface,
  },
  title:       { color: C.text, fontSize: 18, fontWeight: '700' },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  clearBtn:    { padding: 4 },
  clearBtnText:{ color: C.accent, fontSize: 14 },
  empty:       { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyText:   { color: C.text2, fontSize: 14 },
  entry: {
    backgroundColor: C.card, borderRadius: 8, padding: 10,
    marginBottom: 6, borderWidth: 1, borderColor: C.border,
  },
  entryHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  level:       { fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  time:        { color: C.text3, fontSize: 10, fontFamily: 'monospace' },
  message:     { color: C.text2, fontSize: 12, fontFamily: 'monospace' },
  data:        { color: C.text3, fontSize: 10, fontFamily: 'monospace', marginTop: 4 },
});

// ─── Main styles ──────────────────────────────────────────────────
const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },
  content:   { padding: 16, paddingBottom: 52 },

  sectionLabel: {
    color: C.text3, fontSize: 11, textTransform: 'uppercase',
    letterSpacing: 0.8, marginBottom: 8, marginTop: 4, paddingHorizontal: 2,
  },
  divider: { height: 1, backgroundColor: C.border },

  card: {
    backgroundColor: C.card, borderRadius: 14,
    marginBottom: 20, borderWidth: 1, borderColor: C.border, overflow: 'hidden',
  },

  // Account
  accountRow: {
    flexDirection: 'row', alignItems: 'center',
    padding: 16, gap: 14,
  },
  avatar: {
    width: 52, height: 52, borderRadius: 26,
    backgroundColor: C.accentBg, borderWidth: 2, borderColor: C.accent,
    alignItems: 'center', justifyContent: 'center',
  },
  avatarText:   { color: C.accent, fontWeight: '800', fontSize: 18 },
  accountName:  { color: C.text, fontSize: 16, fontWeight: '700' },
  accountEmail: { color: C.text2, fontSize: 12, marginTop: 2 },
  signOutRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    padding: 14, paddingHorizontal: 16,
  },
  signOutText: { color: C.red, fontWeight: '600', fontSize: 14 },

  emptyStores: { padding: 24, alignItems: 'center' },
  emptyStoresText: { color: C.text2, fontSize: 14 },

  // Store rows
  storeRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 14, gap: 12,
  },
  storeRowActive: { backgroundColor: C.accentBg },
  storePrefix: {
    width: 38, height: 38, borderRadius: 8,
    backgroundColor: C.surface, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: C.border,
  },
  storePrefixActive:     { backgroundColor: C.accentBg, borderColor: C.accent },
  storePrefixText:       { color: C.text3, fontWeight: '800', fontSize: 12, fontFamily: 'monospace' },
  storePrefixTextActive: { color: C.accent },
  storeName:             { color: C.text2, fontSize: 14, fontWeight: '600' },
  storeNameActive:       { color: C.text },
  storeMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 3 },
  roleBadge: {
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4,
    borderWidth: 1, borderColor: C.border, backgroundColor: C.surface,
  },
  roleBadgeText: { color: C.text3, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  storeAddr:     { color: C.text3, fontSize: 11 },
  storeRight:    { alignItems: 'flex-end', gap: 4 },
  pendingBadge: {
    backgroundColor: C.accent, borderRadius: 10,
    minWidth: 20, height: 20, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 5,
  },
  pendingBadgeText: { color: C.bg, fontSize: 11, fontWeight: '800' },

  inviteRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 16, paddingVertical: 10,
    backgroundColor: C.surface,
  },
  inviteLabel: { color: C.text3, fontSize: 11 },
  inviteCode:  { color: C.accent, fontSize: 14, fontWeight: '800', fontFamily: 'monospace', letterSpacing: 2 },
  reviewBtnText: { color: C.yellow, fontSize: 12, fontWeight: '600' },

  // Action rows
  actionRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 14, gap: 12,
  },
  actionIcon: {
    width: 36, height: 36, borderRadius: 9,
    backgroundColor: C.accentBg, alignItems: 'center', justifyContent: 'center',
    borderWidth: 1, borderColor: C.border,
  },
  actionTitle: { color: C.text, fontSize: 14, fontWeight: '600' },
  actionHint:  { color: C.text3, fontSize: 11, marginTop: 2 },

  // Connection
  statusRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingTop: 14, paddingBottom: 4,
  },
  statusLabel: { color: C.text, fontSize: 14, fontWeight: '500' },
  apiUrl: { color: C.text3, fontSize: 11, marginTop: 3, fontFamily: 'monospace' },
  statusBadge: {
    flexDirection: 'row', alignItems: 'center',
    borderWidth: 1, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 4, gap: 5,
  },
  statusDot:  { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 12, fontWeight: '700' },
  retryRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    padding: 12, paddingHorizontal: 16, justifyContent: 'center',
  },
  retryText: { color: C.text2, fontSize: 13 },

  version: { color: C.text3, textAlign: 'center', fontSize: 11, marginTop: 4, opacity: 0.6 },
});

// ─── Modal styles (shared) ────────────────────────────────────────
const m = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg, padding: 20 },
  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 24,
  },
  title:        { color: C.text, fontSize: 20, fontWeight: '700' },
  storeSubtitle:{ color: C.text2, fontSize: 13, marginBottom: 20, marginTop: -12 },

  label:    { color: C.text2, fontSize: 12, marginBottom: 6, marginTop: 18 },
  optional: { color: C.text3 },
  input: {
    backgroundColor: C.surface, borderWidth: 1, borderColor: C.border,
    borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12,
    color: C.text, fontSize: 15,
  },
  hint:  { color: C.text3, fontSize: 12, marginTop: 8, lineHeight: 18 },
  error: { color: C.red, fontSize: 13, marginTop: 8 },

  btn: {
    backgroundColor: C.accent, padding: 16,
    borderRadius: 12, alignItems: 'center', marginTop: 22,
  },
  btnDisabled: { opacity: 0.4 },
  btnText:     { color: C.bg, fontWeight: '700', fontSize: 15 },
  ghostBtn:    { alignItems: 'center', padding: 14 },
  ghostBtnText:{ color: C.text2, fontSize: 14 },

  storePreview: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: C.surface, borderRadius: 10,
    padding: 14, gap: 12, marginTop: 8,
    borderWidth: 1, borderColor: C.border,
  },
  previewPrefix: { color: C.accent, fontSize: 18, fontWeight: '800', fontFamily: 'monospace', width: 36 },
  previewName:   { color: C.text, fontSize: 15, fontWeight: '600' },
  previewAddr:   { color: C.text2, fontSize: 12, marginTop: 2 },

  successWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingBottom: 40 },
  successTitle:{ color: C.text, fontSize: 20, fontWeight: '700' },
  successText: { color: C.text2, fontSize: 14, textAlign: 'center', marginTop: 10, lineHeight: 22, paddingHorizontal: 20 },

  requestCard: {
    backgroundColor: C.card, borderRadius: 10, padding: 14,
    marginBottom: 10, borderWidth: 1, borderColor: C.border,
  },
  requestInfo:    { marginBottom: 12 },
  requestName:    { color: C.text, fontSize: 15, fontWeight: '700' },
  requestEmail:   { color: C.text2, fontSize: 13, marginTop: 2 },
  requestMessage: { color: C.text2, fontSize: 13, marginTop: 6, fontStyle: 'italic' },
  requestDate:    { color: C.text3, fontSize: 11, marginTop: 6 },
  requestActions: { flexDirection: 'row', gap: 10 },
  approveBtn: {
    flex: 1, backgroundColor: C.greenBg,
    borderWidth: 1, borderColor: C.green,
    borderRadius: 8, padding: 10, alignItems: 'center',
  },
  approveBtnText: { color: C.green, fontWeight: '700', fontSize: 14 },
  denyBtn: {
    flex: 1, backgroundColor: C.redBg,
    borderWidth: 1, borderColor: C.red,
    borderRadius: 8, padding: 10, alignItems: 'center',
  },
  denyBtnText: { color: C.red, fontWeight: '700', fontSize: 14 },

  emptyWrap: { alignItems: 'center', marginTop: 60 },
  emptyText: { color: C.text2, fontSize: 15 },
});
