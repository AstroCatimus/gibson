/**
 * Gibson — Settings Screen.
 * Account info, store management (join / create / approve members), sign out.
 *
 * Store system:
 *  - Users belong to one or more stores via gibson_store_member
 *  - Joining requires an invite code + owner/admin approval
 *  - Creating a store makes you the owner (you get the invite code to share)
 *  - Owners/admins see a pending requests badge and can approve/deny
 */

import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Alert,
  ScrollView, ActivityIndicator, TextInput, Modal, FlatList,
} from 'react-native';
import { api } from '../../src/lib/api';
import { supabase } from '../../src/lib/supabase';
import { logger } from '../../src/lib/logger';

const ACCENT  = '#e94560';
const BG      = '#0f0f1a';
const CARD    = '#13131f';
const GREEN   = '#2ecc71';
const YELLOW  = '#f39c12';
const BLUE    = '#3498db';
const SURFACE = '#1a1a2a';

// ─── Small helpers ──────────────────────────────────────────────

function SectionLabel({ children }) {
  return <Text style={s.sectionLabel}>{children}</Text>;
}

function Divider() {
  return <View style={s.divider} />;
}

// ─── Main screen ────────────────────────────────────────────────

export default function SettingsScreen() {
  const [user, setUser]             = useState(null);
  const [myStores, setMyStores]     = useState([]);
  const [activeStoreId, setActiveStoreId] = useState('');
  const [loadingStores, setLoadingStores] = useState(true);
  const [apiStatus, setApiStatus]   = useState(null);
  const [checking, setChecking]     = useState(false);

  // Modal visibility
  const [showJoin, setShowJoin]     = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showRequests, setShowRequests] = useState(null); // store_id or null
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

      {/* ── Account ── */}
      <View style={s.card}>
        <Text style={s.cardLabel}>Account</Text>
        <View style={s.accountRow}>
          <View style={s.avatar}>
            <Text style={s.avatarText}>{initials}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.accountName}>{displayName || 'Gibson User'}</Text>
            <Text style={s.accountEmail}>{user?.email || ''}</Text>
          </View>
        </View>
        <TouchableOpacity style={s.signOutBtn} onPress={handleSignOut}>
          <Text style={s.signOutText}>Sign Out</Text>
        </TouchableOpacity>
      </View>

      {/* ── My Stores ── */}
      <SectionLabel>Your Stores</SectionLabel>
      <View style={s.card}>
        {loadingStores ? (
          <ActivityIndicator color={ACCENT} style={{ margin: 16 }} />
        ) : myStores.length === 0 ? (
          <View style={s.noStoresWrap}>
            <Text style={s.noStoresText}>You haven't joined any stores yet.</Text>
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
                >
                  <View style={[s.storePrefix, active && s.storePrefixActive]}>
                    <Text style={[s.storePrefixText, active && s.storePrefixTextActive]}>
                      {store.prefix}
                    </Text>
                  </View>

                  <View style={{ flex: 1 }}>
                    <Text style={[s.storeName, active && s.storeNameActive]}>
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
                    {active && <Text style={s.storeCheck}>✓</Text>}
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

                {/* Invite code — only visible to owner/admin */}
                {isAdmin && store.invite_code && (
                  <View style={s.inviteRow}>
                    <Text style={s.inviteLabel}>Invite code</Text>
                    <Text style={s.inviteCode}>{store.invite_code}</Text>
                    {isAdmin && pending > 0 && (
                      <TouchableOpacity
                        style={s.reviewBtn}
                        onPress={() => setShowRequests(store.store_id)}
                      >
                        <Text style={s.reviewBtnText}>
                          {pending} pending →
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>
                )}
              </View>
            );
          })
        )}
      </View>

      {/* ── Join / Create ── */}
      <SectionLabel>Find a Store</SectionLabel>
      <View style={s.card}>
        <TouchableOpacity style={s.actionRow} onPress={() => setShowJoin(true)}>
          <View style={s.actionIcon}><Text style={s.actionIconText}>🔑</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={s.actionTitle}>Join with Invite Code</Text>
            <Text style={s.actionHint}>Enter the 6-character code from your store owner</Text>
          </View>
          <Text style={s.actionChevron}>›</Text>
        </TouchableOpacity>
        <Divider />
        <TouchableOpacity style={s.actionRow} onPress={() => setShowCreate(true)}>
          <View style={s.actionIcon}><Text style={s.actionIconText}>🏪</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={s.actionTitle}>Create a Store</Text>
            <Text style={s.actionHint}>Start a new store — you'll be the owner</Text>
          </View>
          <Text style={s.actionChevron}>›</Text>
        </TouchableOpacity>
      </View>

      {/* ── API status ── */}
      <SectionLabel>Connection</SectionLabel>
      <View style={s.card}>
        <View style={s.statusRow}>
          <View style={{ flex: 1 }}>
            <Text style={s.statusLabel}>API Server</Text>
            <Text style={s.apiUrl}>{process.env.EXPO_PUBLIC_API_BASE_URL}</Text>
          </View>
          {checking
            ? <ActivityIndicator color={ACCENT} size="small" />
            : (
              <View style={[s.statusBadge, { borderColor: apiStatus === 'ok' ? GREEN : '#e74c3c' }]}>
                <View style={[s.statusDot, { backgroundColor: apiStatus === 'ok' ? GREEN : '#e74c3c' }]} />
                <Text style={[s.statusText, { color: apiStatus === 'ok' ? GREEN : '#e74c3c' }]}>
                  {apiStatus === 'ok' ? 'Online' : 'Offline'}
                </Text>
              </View>
            )
          }
        </View>
        <TouchableOpacity onPress={checkApi} style={s.retryBtn}>
          <Text style={s.retryBtnText}>Check Again</Text>
        </TouchableOpacity>
      </View>

      {/* ── Debug ── */}
      <SectionLabel>Developer</SectionLabel>
      <View style={s.card}>
        <TouchableOpacity style={s.actionRow} onPress={() => setShowLogs(true)}>
          <View style={s.actionIcon}><Text style={s.actionIconText}>🪵</Text></View>
          <View style={{ flex: 1 }}>
            <Text style={s.actionTitle}>Debug Logs</Text>
            <Text style={s.actionHint}>API calls, errors, auth events</Text>
          </View>
          <Text style={s.actionChevron}>›</Text>
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
        onSuccess={(newStore) => {
          setShowCreate(false);
          loadStores();
          switchStore(newStore.store_id);
        }}
      />
      <LogsModal visible={showLogs} onClose={() => setShowLogs(false)} />

      {showRequests && (
        <RequestsModal
          storeId={showRequests}
          storeName={myStores.find(s => s.store_id === showRequests)?.name || ''}
          onClose={() => { setShowRequests(null); loadStores(); }}
        />
      )}
    </ScrollView>
  );
}

// ─── Join Store Modal ────────────────────────────────────────────

function JoinModal({ visible, onClose, onSuccess }) {
  const [code, setCode]         = useState('');
  const [message, setMessage]   = useState('');
  const [found, setFound]       = useState(null);   // store preview
  const [step, setStep]         = useState('code'); // 'code' | 'confirm' | 'sent'
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  function reset() {
    setCode(''); setMessage(''); setFound(null);
    setStep('code'); setError('');
  }

  async function handleLookup() {
    if (code.trim().length < 4) { setError('Enter the full invite code.'); return; }
    setLoading(true); setError('');
    try {
      const result = await api.lookupStoreByCode(code.trim());
      if (result.membership?.status === 'active') {
        setError("You're already a member of this store.");
        setLoading(false); return;
      }
      if (result.join_request?.status === 'pending') {
        setError('You already have a pending request for this store.');
        setLoading(false); return;
      }
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
            <Text style={m.closeBtn}>✕</Text>
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
              placeholderTextColor="#444"
              autoCapitalize="characters"
              maxLength={8}
            />
            {error ? <Text style={m.error}>{error}</Text> : null}
            <TouchableOpacity
              style={[m.btn, (!code.trim() || loading) && m.btnDisabled]}
              onPress={handleLookup}
              disabled={!code.trim() || loading}
            >
              {loading
                ? <ActivityIndicator color="#fff" />
                : <Text style={m.btnText}>Find Store</Text>
              }
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
              placeholder="Hi, I'm a new employee at the store…"
              placeholderTextColor="#444"
              multiline
            />
            {error ? <Text style={m.error}>{error}</Text> : null}

            <Text style={m.hint}>
              Your request will be sent to the store owner for approval.
              You'll need to re-open settings to confirm once approved.
            </Text>

            <TouchableOpacity
              style={[m.btn, loading && m.btnDisabled]}
              onPress={handleSubmit}
              disabled={loading}
            >
              {loading
                ? <ActivityIndicator color="#fff" />
                : <Text style={m.btnText}>Send Join Request</Text>
              }
            </TouchableOpacity>
            <TouchableOpacity style={m.ghostBtn} onPress={() => setStep('code')}>
              <Text style={m.ghostBtnText}>← Back</Text>
            </TouchableOpacity>
          </>
        )}

        {step === 'sent' && (
          <View style={m.successWrap}>
            <Text style={m.successIcon}>📬</Text>
            <Text style={m.successTitle}>Request Sent</Text>
            <Text style={m.successText}>
              The store owner will review your request. Check back in Settings once they've responded.
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

// ─── Create Store Modal ──────────────────────────────────────────

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
    if (!/^[A-Za-z]{1,4}$/.test(prefix.trim())) {
      setError('Prefix must be 1–4 letters only.');
      return;
    }
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
            <Text style={m.closeBtn}>✕</Text>
          </TouchableOpacity>
        </View>

        <Text style={m.label}>Store Name</Text>
        <TextInput
          style={m.input}
          value={name}
          onChangeText={setName}
          placeholder="Driftless Books & Music"
          placeholderTextColor="#444"
        />

        <Text style={m.label}>Address <Text style={m.optional}>(optional)</Text></Text>
        <TextInput
          style={m.input}
          value={address}
          onChangeText={setAddress}
          placeholder="518 Walnut St, Viroqua WI"
          placeholderTextColor="#444"
        />

        <Text style={m.label}>SKU Prefix</Text>
        <TextInput
          style={m.input}
          value={prefix}
          onChangeText={t => setPrefix(t.toUpperCase())}
          placeholder="DL"
          placeholderTextColor="#444"
          autoCapitalize="characters"
          maxLength={4}
        />
        <Text style={m.hint}>
          2–4 letters that appear at the start of every SKU (e.g. DL-1234).
          Each store must have a unique prefix.
        </Text>

        {error ? <Text style={m.error}>{error}</Text> : null}

        <TouchableOpacity
          style={[m.btn, (!name.trim() || !prefix.trim() || loading) && m.btnDisabled]}
          onPress={handleCreate}
          disabled={!name.trim() || !prefix.trim() || loading}
        >
          {loading
            ? <ActivityIndicator color="#fff" />
            : <Text style={m.btnText}>Create Store</Text>
          }
        </TouchableOpacity>
        <TouchableOpacity style={m.ghostBtn} onPress={() => { reset(); onClose(); }}>
          <Text style={m.ghostBtnText}>Cancel</Text>
        </TouchableOpacity>
      </View>
    </Modal>
  );
}

// ─── Pending Requests Modal ──────────────────────────────────────

function RequestsModal({ storeId, storeName, onClose }) {
  const [requests, setRequests] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [acting, setActing]     = useState(null); // request_id being acted on

  useEffect(() => { loadRequests(); }, []);

  async function loadRequests() {
    setLoading(true);
    try {
      const { requests: reqs } = await api.getJoinRequests(storeId);
      setRequests(reqs || []);
    } catch {
      setRequests([]);
    } finally {
      setLoading(false);
    }
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
            <Text style={m.closeBtn}>✕</Text>
          </TouchableOpacity>
        </View>

        <Text style={m.storeSubtitle}>{storeName}</Text>

        {loading ? (
          <ActivityIndicator color={ACCENT} style={{ marginTop: 40 }} />
        ) : requests.length === 0 ? (
          <View style={m.emptyWrap}>
            <Text style={m.emptyIcon}>✅</Text>
            <Text style={m.emptyText}>No pending requests</Text>
          </View>
        ) : (
          <ScrollView style={{ flex: 1 }}>
            {requests.map(req => (
              <View key={req.request_id} style={m.requestCard}>
                <View style={m.requestInfo}>
                  <Text style={m.requestName}>{req.user_name || 'Unknown'}</Text>
                  <Text style={m.requestEmail}>{req.user_email}</Text>
                  {req.message ? (
                    <Text style={m.requestMessage}>"{req.message}"</Text>
                  ) : null}
                  <Text style={m.requestDate}>
                    {new Date(req.created_at).toLocaleDateString()}
                  </Text>
                </View>
                <View style={m.requestActions}>
                  {acting === req.request_id ? (
                    <ActivityIndicator color={ACCENT} />
                  ) : (
                    <>
                      <TouchableOpacity
                        style={m.approveBtn}
                        onPress={() => handle(req.request_id, 'approve')}
                      >
                        <Text style={m.approveBtnText}>Approve</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={m.denyBtn}
                        onPress={() => handle(req.request_id, 'deny')}
                      >
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

// ─── Logs Modal ─────────────────────────────────────────────────

const LOG_COLORS = {
  error: '#e74c3c',
  warn:  '#f39c12',
  info:  '#3498db',
  debug: '#555',
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
            <TouchableOpacity onPress={onClose} style={{ padding: 4 }}>
              <Text style={lm.closeBtn}>✕</Text>
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
                  <Text style={lm.time}>
                    {new Date(item.timestamp).toLocaleTimeString()}
                  </Text>
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

const lm = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', padding: 16,
    borderBottomWidth: 1, borderBottomColor: '#1a1a2a',
  },
  title: { color: '#fff', fontSize: 18, fontWeight: '700' },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  clearBtn: { padding: 4 },
  clearBtnText: { color: ACCENT, fontSize: 14 },
  closeBtn: { color: '#555', fontSize: 20 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyText: { color: '#555', fontSize: 14 },
  entry: {
    backgroundColor: CARD, borderRadius: 8, padding: 10,
    marginBottom: 6, borderWidth: 1, borderColor: '#1e1e2e',
  },
  entryHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  level: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  time: { color: '#444', fontSize: 10, fontFamily: 'monospace' },
  message: { color: '#ccc', fontSize: 12, fontFamily: 'monospace' },
  data: { color: '#555', fontSize: 10, fontFamily: 'monospace', marginTop: 4 },
});

// ─── Styles ──────────────────────────────────────────────────────

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  content: { padding: 16, paddingBottom: 48 },

  sectionLabel: {
    color: '#444', fontSize: 11, textTransform: 'uppercase',
    letterSpacing: 1, marginBottom: 8, marginTop: 4, paddingHorizontal: 2,
  },
  divider: { height: 1, backgroundColor: '#1a1a2a', marginHorizontal: 0 },

  card: {
    backgroundColor: CARD, borderRadius: 12,
    marginBottom: 20, borderWidth: 1, borderColor: '#1e1e2e', overflow: 'hidden',
  },
  cardLabel: {
    color: '#444', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1,
    paddingHorizontal: 16, paddingTop: 14, paddingBottom: 12,
  },

  accountRow: {
    flexDirection: 'row', alignItems: 'flex-start',
    paddingHorizontal: 16, paddingBottom: 16, gap: 14,
  },
  avatar: {
    width: 52, height: 52, borderRadius: 26,
    backgroundColor: ACCENT, alignItems: 'center', justifyContent: 'center',
  },
  avatarText: { color: '#fff', fontWeight: '800', fontSize: 18 },
  accountName: { color: '#fff', fontSize: 16, fontWeight: '700' },
  accountEmail: { color: '#555', fontSize: 12, marginTop: 2 },
  signOutBtn: {
    marginHorizontal: 16, marginBottom: 14,
    borderWidth: 1, borderColor: '#3a1515',
    borderRadius: 8, padding: 10, alignItems: 'center', backgroundColor: '#1a0808',
  },
  signOutText: { color: '#e74c3c', fontWeight: '700', fontSize: 13 },

  noStoresWrap: { padding: 20, alignItems: 'center' },
  noStoresText: { color: '#555', fontSize: 14 },

  storeRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 14, gap: 12,
  },
  storeRowActive: { backgroundColor: '#160810' },
  storePrefix: {
    width: 36, height: 36, borderRadius: 8,
    backgroundColor: SURFACE, alignItems: 'center', justifyContent: 'center',
  },
  storePrefixActive: { backgroundColor: '#2d0e1a' },
  storePrefixText: { color: '#555', fontWeight: '800', fontSize: 12, fontFamily: 'monospace' },
  storePrefixTextActive: { color: ACCENT },
  storeName: { color: '#888', fontSize: 14, fontWeight: '600' },
  storeNameActive: { color: '#fff' },
  storeMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 3 },
  roleBadge: {
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: 4, borderWidth: 1, borderColor: '#333', backgroundColor: '#1a1a2a',
  },
  roleBadgeText: { color: '#666', fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  storeAddr: { color: '#444', fontSize: 11 },
  storeRight: { alignItems: 'flex-end', gap: 4 },
  storeCheck: { color: ACCENT, fontSize: 16, fontWeight: '700' },
  pendingBadge: {
    backgroundColor: ACCENT, borderRadius: 10,
    minWidth: 20, height: 20, alignItems: 'center', justifyContent: 'center',
    paddingHorizontal: 5,
  },
  pendingBadgeText: { color: '#fff', fontSize: 11, fontWeight: '800' },

  inviteRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 10,
    backgroundColor: '#0c0c17', gap: 8,
  },
  inviteLabel: { color: '#444', fontSize: 11 },
  inviteCode: {
    color: ACCENT, fontSize: 14, fontWeight: '800',
    fontFamily: 'monospace', letterSpacing: 2,
  },
  reviewBtn: { marginLeft: 'auto' },
  reviewBtnText: { color: YELLOW, fontSize: 12, fontWeight: '600' },

  actionRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 14, gap: 12,
  },
  actionIcon: {
    width: 36, height: 36, borderRadius: 8,
    backgroundColor: SURFACE, alignItems: 'center', justifyContent: 'center',
  },
  actionIconText: { fontSize: 18 },
  actionTitle: { color: '#fff', fontSize: 14, fontWeight: '600' },
  actionHint: { color: '#555', fontSize: 11, marginTop: 2 },
  actionChevron: { color: '#444', fontSize: 22 },

  statusRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingTop: 14, paddingBottom: 4,
  },
  statusLabel: { color: '#888', fontSize: 14 },
  apiUrl: { color: '#444', fontSize: 11, marginTop: 2, fontFamily: 'monospace' },
  statusBadge: {
    flexDirection: 'row', alignItems: 'center',
    borderWidth: 1, borderRadius: 20,
    paddingHorizontal: 10, paddingVertical: 4, gap: 5,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 12, fontWeight: '700' },
  retryBtn: {
    marginHorizontal: 16, marginBottom: 14, marginTop: 10,
    padding: 8, borderRadius: 8, backgroundColor: SURFACE, alignItems: 'center',
  },
  retryBtnText: { color: '#888', fontSize: 13 },

  version: { color: '#2a2a3a', textAlign: 'center', fontSize: 11, marginTop: 4 },
});

// Modal styles (shared across all three modals)
const m = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG, padding: 20 },
  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 24,
  },
  title: { color: '#fff', fontSize: 20, fontWeight: '700' },
  closeBtn: { color: '#555', fontSize: 22, padding: 4 },
  storeSubtitle: { color: '#888', fontSize: 13, marginBottom: 20, marginTop: -12 },

  label: { color: '#888', fontSize: 12, marginBottom: 6, marginTop: 16 },
  optional: { color: '#444' },
  input: {
    backgroundColor: SURFACE, borderWidth: 1, borderColor: '#252535',
    borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12,
    color: '#fff', fontSize: 15,
  },
  hint: { color: '#444', fontSize: 12, marginTop: 8, lineHeight: 18 },
  error: { color: '#e74c3c', fontSize: 13, marginTop: 8 },

  btn: {
    backgroundColor: ACCENT, padding: 16,
    borderRadius: 12, alignItems: 'center', marginTop: 20,
  },
  btnDisabled: { opacity: 0.4 },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  ghostBtn: { alignItems: 'center', padding: 14 },
  ghostBtnText: { color: '#555', fontSize: 14 },

  storePreview: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: SURFACE, borderRadius: 10,
    padding: 14, gap: 12, marginTop: 8,
    borderWidth: 1, borderColor: '#252535',
  },
  previewPrefix: {
    color: ACCENT, fontSize: 18, fontWeight: '800',
    fontFamily: 'monospace', width: 36,
  },
  previewName: { color: '#fff', fontSize: 15, fontWeight: '600' },
  previewAddr: { color: '#555', fontSize: 12, marginTop: 2 },

  successWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingBottom: 40 },
  successIcon: { fontSize: 56, marginBottom: 16 },
  successTitle: { color: '#fff', fontSize: 20, fontWeight: '700' },
  successText: {
    color: '#888', fontSize: 14, textAlign: 'center',
    marginTop: 10, lineHeight: 22, paddingHorizontal: 20,
  },

  // Requests modal
  requestCard: {
    backgroundColor: CARD, borderRadius: 10,
    padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: '#1e1e2e',
  },
  requestInfo: { marginBottom: 12 },
  requestName: { color: '#fff', fontSize: 15, fontWeight: '700' },
  requestEmail: { color: '#888', fontSize: 13, marginTop: 2 },
  requestMessage: { color: '#aaa', fontSize: 13, marginTop: 6, fontStyle: 'italic' },
  requestDate: { color: '#444', fontSize: 11, marginTop: 6 },
  requestActions: { flexDirection: 'row', gap: 10 },
  approveBtn: {
    flex: 1, backgroundColor: '#0d2a15',
    borderWidth: 1, borderColor: GREEN,
    borderRadius: 8, padding: 10, alignItems: 'center',
  },
  approveBtnText: { color: GREEN, fontWeight: '700', fontSize: 14 },
  denyBtn: {
    flex: 1, backgroundColor: '#1a0808',
    borderWidth: 1, borderColor: '#e74c3c',
    borderRadius: 8, padding: 10, alignItems: 'center',
  },
  denyBtnText: { color: '#e74c3c', fontWeight: '700', fontSize: 14 },

  emptyWrap: { alignItems: 'center', marginTop: 60 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyText: { color: '#555', fontSize: 15 },
});
