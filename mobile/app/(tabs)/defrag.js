/**
 * Gibson — Defrag / Shelf Verification Tab.
 * Walk inventory section by section, card by card.
 * FOUND ✓ | FOUND—UPDATE | NOT FOUND | SKIP
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Modal, TextInput, Alert, Linking,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { router } from 'expo-router';
import { api } from '../../src/lib/api';

const ACCENT  = '#e94560';
const BG      = '#0f0f1a';
const CARD    = '#13131f';
const GREEN   = '#2ecc71';
const YELLOW  = '#f39c12';
const RED     = '#e74c3c';
const BLUE    = '#3498db';
const PURPLE  = '#9b59b6';
const INACTIVE = '#333';
const MUTED    = '#888';

// ─── Tier badge ──────────────────────────────────────────────
function TierBadge({ tier }) {
  const colors = { 1: GREEN, 2: BLUE, 3: PURPLE };
  const labels = { 1: 'Gibson', 2: 'Amazon', 3: 'Ka-Zam' };
  const c = colors[tier] || '#555';
  return (
    <View style={[tb.badge, { borderColor: c, backgroundColor: c + '22' }]}>
      <Text style={[tb.text, { color: c }]}>T{tier} · {labels[tier]}</Text>
    </View>
  );
}
const tb = StyleSheet.create({
  badge: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 7, paddingVertical: 2 },
  text: { fontSize: 10, fontWeight: '700' },
});

// ─── Progress bar ─────────────────────────────────────────────
function ProgressBar({ pct, color = GREEN }) {
  return (
    <View style={pb.track}>
      <View style={[pb.fill, { width: `${Math.min(100, pct)}%`, backgroundColor: color }]} />
    </View>
  );
}
const pb = StyleSheet.create({
  track: { height: 5, backgroundColor: '#1a1a2a', borderRadius: 3, overflow: 'hidden', flex: 1 },
  fill:  { height: '100%', borderRadius: 3 },
});


// ═══════════════════════════════════════════════════════════════
// Main screen
// ═══════════════════════════════════════════════════════════════
export default function DefragScreen() {
  const [view, setView]         = useState('dashboard');   // dashboard | queue | missing
  const [stats, setStats]       = useState(null);
  const [sections, setSections] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [showEmpty, setShowEmpty] = useState(false);

  // Queue state
  const [activeSection, setActiveSection]     = useState(null);
  const [sessionId, setSessionId]             = useState(null);
  const [queue, setQueue]                     = useState([]);
  const [queueOffset, setQueueOffset]         = useState(0);
  const [queueTotal, setQueueTotal]           = useState(0);
  const [queueLoading, setQueueLoading]       = useState(false);
  const [cardIndex, setCardIndex]             = useState(0);

  // Update modal
  const [updateModal, setUpdateModal]         = useState(false);
  const [updateItem, setUpdateItem]           = useState(null);
  const [updatePrice, setUpdatePrice]         = useState('');
  const [updateCondition, setUpdateCondition] = useState('');

  // Missing state
  const [missing, setMissing]                 = useState([]);
  const [missingLoading, setMissingLoading]   = useState(false);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const [s, sec] = await Promise.all([api.defragStats(), api.defragSections()]);
      setStats(s);
      setSections(sec);
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  // ── Start verification session for a section ─────────────────
  async function startSection(section) {
    try {
      const sess = await api.defragStartSession(section.section);
      setSessionId(sess.session_id);
      setActiveSection(section);
      setCardIndex(0);
      setQueueOffset(0);
      await loadQueue(section.section, 0);
      setView('queue');
    } catch (e) {
      Alert.alert('Error', e.message);
    }
  }

  async function loadQueue(sectionName, offset) {
    setQueueLoading(true);
    try {
      const params = `?section=${encodeURIComponent(sectionName)}&limit=20&offset=${offset}`;
      const data = await api.defragQueue(params);
      if (offset === 0) {
        setQueue(data.items);
      } else {
        setQueue(prev => [...prev, ...data.items]);
      }
      setQueueTotal(data.total);
      setQueueOffset(offset + data.items.length);
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setQueueLoading(false);
    }
  }

  // ── Verification actions ──────────────────────────────────────
  async function verifyAction(action, extras = {}) {
    const item = queue[cardIndex];
    if (!item) return;
    try {
      await api.defragVerify(item.stock_item_id, action, {
        session_id: sessionId,
        ...extras,
      });
      advanceCard();
    } catch (e) {
      Alert.alert('Error', e.message);
    }
  }

  function advanceCard() {
    const next = cardIndex + 1;
    if (next >= queue.length && queueOffset < queueTotal) {
      loadQueue(activeSection.section, queueOffset);
    }
    if (next >= queue.length) {
      finishSession();
    } else {
      setCardIndex(next);
    }
  }

  async function finishSession() {
    if (sessionId) await api.defragEndSession(sessionId).catch(() => {});
    setSessionId(null);
    setView('dashboard');
    loadDashboard();
    Alert.alert('Section Complete', `All items in "${activeSection?.section}" reviewed.`);
    setActiveSection(null);
  }

  // ── Missing queue ─────────────────────────────────────────────
  async function loadMissing() {
    setMissingLoading(true);
    try {
      const data = await api.defragMissing();
      setMissing(data);
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setMissingLoading(false);
    }
  }

  function openMissing() {
    setView('missing');
    loadMissing();
  }

  // ── Import ────────────────────────────────────────────────────
  const [importSource, setImportSource]   = useState('kazam');
  const [importJob, setImportJob]         = useState(null);   // { job_id, status, pct, created, ... }
  const [importLoading, setImportLoading] = useState(false);
  const importPollRef = React.useRef(null);

  function stopPolling() {
    if (importPollRef.current) {
      clearInterval(importPollRef.current);
      importPollRef.current = null;
    }
  }

  async function pollJobStatus(jobId) {
    try {
      const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000';
      const resp = await fetch(`${BASE_URL}/api/import/status/${jobId}`);
      if (!resp.ok) return;
      const data = await resp.json();
      setImportJob(data);
      if (data.done) {
        stopPolling();
        setImportLoading(false);
        loadDashboard();
      }
    } catch (e) {
      // network blip — keep polling
    }
  }

  async function pickAndImport(source) {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['text/csv', 'text/tab-separated-values', 'text/plain', '*/*'],
        copyToCacheDirectory: true,
      });
      if (result.canceled) return;

      const asset = result.assets[0];
      setImportLoading(true);
      setImportJob(null);

      const { supabase } = await import('../../src/lib/supabase');
      const { data: { session } } = await supabase.auth.getSession();
      const meta = session?.user?.user_metadata || {};

      const formData = new FormData();
      formData.append('file', {
        uri: asset.uri,
        name: asset.name,
        type: asset.mimeType || 'text/csv',
      });
      formData.append('dry_run', 'false');

      const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000';
      const resp = await fetch(`${BASE_URL}/api/import/${source}`, {
        method: 'POST',
        headers: {
          'X-Store-Id':       meta.store_id || '',
          'X-Employee-Id':    session?.user?.id || '',
          'X-Employee-Email': session?.user?.email || '',
        },
        body: formData,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const { job_id } = await resp.json();

      // Start polling every 2 seconds
      setImportJob({ job_id, status: 'running', pct: 0, created: 0, skipped: 0, errors: 0 });
      stopPolling();
      importPollRef.current = setInterval(() => pollJobStatus(job_id), 2000);

    } catch (e) {
      setImportLoading(false);
      Alert.alert('Import Error', e.message);
    }
  }

  async function resolveMissing(item, resolution) {
    try {
      await api.defragResolveMissing(item.stock_item_id, resolution);
      setMissing(prev => prev.filter(m => m.stock_item_id !== item.stock_item_id));
    } catch (e) {
      Alert.alert('Error', e.message);
    }
  }

  // ════════════════════════════════════════════════════════════
  // RENDER
  // ════════════════════════════════════════════════════════════

  if (view === 'import') {
    return (
      <ScrollView style={s.container} contentContainerStyle={[s.content, { paddingTop: 56 }]}>
        <TouchableOpacity onPress={() => setView('dashboard')}>
          <Text style={{ color: ACCENT, fontSize: 14, marginBottom: 20 }}>← Back</Text>
        </TouchableOpacity>
        <Text style={{ color: '#fff', fontSize: 18, fontWeight: '700', marginBottom: 4 }}>
          Import Inventory
        </Text>
        <Text style={{ color: '#555', fontSize: 13, marginBottom: 24 }}>
          Upload a CSV or TSV export from Amazon or Ka-Zam. Each row becomes a stock item with trust tier 2 (Amazon) or 3 (Ka-Zam).
        </Text>

        {/* Source selector */}
        <View style={imp.sourceRow}>
          {[['kazam', 'Ka-Zam', PURPLE], ['amazon', 'Amazon', BLUE]].map(([key, label, color]) => (
            <TouchableOpacity
              key={key}
              style={[imp.sourceBtn, importSource === key && { borderColor: color, backgroundColor: color + '22' }]}
              onPress={() => setImportSource(key)}
            >
              <Text style={[imp.sourceTxt, importSource === key && { color }]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={{ color: '#555', fontSize: 12, marginBottom: 16 }}>
          {importSource === 'kazam'
            ? 'Ka-Zam export: CSV with columns for ISBN, Title, Author, Location, Price, Condition.'
            : 'Amazon Seller Central: flat-file inventory report TSV (Get Report → Active Listings).'}
        </Text>

        <TouchableOpacity
          style={[imp.uploadBtn, importLoading && { opacity: 0.5 }]}
          onPress={() => pickAndImport(importSource)}
          disabled={importLoading}
        >
          {importLoading && !importJob
            ? <ActivityIndicator color="#fff" />
            : <Text style={imp.uploadTxt}>Choose File & Import</Text>
          }
        </TouchableOpacity>

        {importJob && (
          <View style={imp.resultCard}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text style={imp.resultTitle}>
                {importJob.done
                  ? (importJob.status === 'failed' ? '✗ Import Failed' : '✓ Import Complete')
                  : '⟳ Importing…'}
              </Text>
              <Text style={{ color: MUTED, fontSize: 12 }}>{importJob.pct ?? 0}%</Text>
            </View>

            {/* Progress bar */}
            <View style={pb.track}>
              <View style={[pb.fill, {
                width: `${importJob.pct ?? 0}%`,
                backgroundColor: importJob.status === 'failed' ? RED : importJob.done ? GREEN : ACCENT,
              }]} />
            </View>

            <Text style={{ color: MUTED, fontSize: 11, marginTop: 6, marginBottom: 12 }}>
              {importJob.processed ?? 0} / {importJob.total ?? '?'} rows processed
            </Text>

            <View style={imp.resultRow}>
              <ResultStat label="Created" value={importJob.created ?? 0}  color={GREEN} />
              <ResultStat label="Skipped" value={importJob.skipped ?? 0}  color={YELLOW} />
              <ResultStat label="Errors"  value={importJob.errors  ?? 0}  color={RED} />
            </View>

            {importJob.error_details?.length > 0 && (
              <>
                <Text style={{ color: RED, fontSize: 12, marginTop: 12, marginBottom: 6 }}>First errors:</Text>
                {importJob.error_details.map((e, i) => (
                  <Text key={i} style={{ color: '#666', fontSize: 11 }}>
                    Row {e.row}: {e.error}
                  </Text>
                ))}
              </>
            )}
          </View>
        )}
      </ScrollView>
    );
  }

  if (view === 'queue') {
    return (
      <QueueView
        section={activeSection}
        queue={queue}
        cardIndex={cardIndex}
        queueTotal={queueTotal}
        queueLoading={queueLoading}
        onFound={() => verifyAction('FOUND')}
        onFoundUpdate={() => {
          setUpdateItem(queue[cardIndex]);
          setUpdatePrice(String(queue[cardIndex]?.asking_price || ''));
          setUpdateCondition(queue[cardIndex]?.condition_grade || '');
          setUpdateModal(true);
        }}
        onNotFound={() => verifyAction('NOT_FOUND')}
        onSkip={() => verifyAction('SKIP')}
        onExit={() => { setView('dashboard'); loadDashboard(); }}
        updateModal={updateModal}
        setUpdateModal={setUpdateModal}
        updateItem={updateItem}
        updatePrice={updatePrice}
        setUpdatePrice={setUpdatePrice}
        updateCondition={updateCondition}
        setUpdateCondition={setUpdateCondition}
        onUpdateConfirm={() => {
          setUpdateModal(false);
          verifyAction('FOUND_UPDATE', {
            asking_price: parseFloat(updatePrice) || undefined,
            condition_grade: updateCondition || undefined,
          });
        }}
      />
    );
  }

  if (view === 'missing') {
    return (
      <MissingView
        missing={missing}
        loading={missingLoading}
        onResolve={resolveMissing}
        onBack={() => setView('dashboard')}
      />
    );
  }

  // ── Dashboard ─────────────────────────────────────────────────
  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* Stats header */}
      {loading ? (
        <ActivityIndicator color={ACCENT} style={{ marginTop: 40 }} />
      ) : stats ? (
        <View style={s.statsCard}>
          <Text style={s.statsTitle}>Shelf Verification</Text>
          <View style={s.statsRow}>
            <ProgressBar pct={stats.pct_complete} />
            <Text style={s.statsPct}>{stats.pct_complete}%</Text>
          </View>
          <View style={s.statsGrid}>
            <StatBox label="Total"     value={stats.total}     color="#aaa" />
            <StatBox label="Verified"  value={stats.verified}  color={GREEN} />
            <StatBox label="Missing"   value={stats.missing}   color={RED} />
            <StatBox label="Remaining" value={stats.unverified} color={YELLOW} />
          </View>
          <View style={s.tierRow}>
            <Text style={s.tierLabel}>T1 Gibson</Text>
            <Text style={[s.tierVal, { color: GREEN }]}>{stats.tier_breakdown.tier1}</Text>
            <Text style={s.tierLabel}>T2 Amazon</Text>
            <Text style={[s.tierVal, { color: BLUE }]}>{stats.tier_breakdown.tier2}</Text>
            <Text style={s.tierLabel}>T3 Ka-Zam</Text>
            <Text style={[s.tierVal, { color: PURPLE }]}>{stats.tier_breakdown.tier3}</Text>
          </View>

          {/* Price staleness */}
          {stats.price_staleness && (
            <View style={[s.tierRow, { marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#1e1e2e' }]}>
              <Text style={s.tierLabel}>Legacy</Text>
              <Text style={[s.tierVal, { color: '#e67e22' }]}>{stats.price_staleness.legacy}</Text>
              <Text style={s.tierLabel}>Stale</Text>
              <Text style={[s.tierVal, { color: YELLOW }]}>{stats.price_staleness.stale + stats.price_staleness.aging}</Text>
              <Text style={s.tierLabel}>Fresh</Text>
              <Text style={[s.tierVal, { color: GREEN }]}>{stats.price_staleness.fresh}</Text>
              {stats.unsectioned > 0 && <>
                <Text style={s.tierLabel}>No Section</Text>
                <Text style={[s.tierVal, { color: RED }]}>{stats.unsectioned}</Text>
              </>}
            </View>
          )}
        </View>
      ) : null}

      {/* Quick actions */}
      <View style={s.actionRow}>
        <TouchableOpacity
          style={[s.actionBtn, { borderColor: ACCENT }]}
          onPress={() => setView('import')}
        >
          <Text style={[s.actionBtnText, { color: ACCENT }]}>Import Files</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[s.actionBtn, { borderColor: RED }]}
          onPress={openMissing}
        >
          <Text style={[s.actionBtnText, { color: RED }]}>
            Missing Queue {stats?.missing ? `(${stats.missing})` : ''}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[s.actionBtn, { borderColor: BLUE }]}
          onPress={() => Linking.openURL(api.defragExport('amazon', 'verified'))}
        >
          <Text style={[s.actionBtnText, { color: BLUE }]}>Amazon TSV</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[s.actionBtn, { borderColor: PURPLE }]}
          onPress={() => Linking.openURL(api.defragExport('biblio', 'verified'))}
        >
          <Text style={[s.actionBtnText, { color: PURPLE }]}>Biblio TSV</Text>
        </TouchableOpacity>
      </View>

      {/* Section list header + controls */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
        <Text style={s.sectionHeader}>Sections</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {sections.some(s => s.total === 0) && (
            <TouchableOpacity
              onPress={() => {
                Alert.alert(
                  'Clean Up Empty Sections',
                  'Delete all sections with no active inventory?',
                  [
                    { text: 'Cancel', style: 'cancel' },
                    { text: 'Delete All', style: 'destructive', onPress: async () => {
                      try {
                        const r = await api.defragDeleteEmptySections();
                        Alert.alert('Done', `Removed ${r.deleted} empty section${r.deleted !== 1 ? 's' : ''}`);
                        loadDashboard();
                      } catch (e) { Alert.alert('Error', e.message); }
                    }},
                  ]
                );
              }}
            >
              <Text style={{ color: RED, fontSize: 12 }}>Clean up empty</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => setShowEmpty(v => !v)}>
            <Text style={{ color: showEmpty ? ACCENT : '#555', fontSize: 12 }}>
              {showEmpty ? 'Hide empty' : 'Show empty'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading ? null : sections
        .filter(sec => showEmpty || sec.total > 0)
        .map((sec) => {
        const pct = sec.total > 0 ? Math.round(sec.verified / sec.total * 100) : 0;
        const isEmpty = sec.total === 0;
        const hasQueue = sec.unverified > 0;
        return (
          <TouchableOpacity
            key={sec.location_id || sec.section}
            style={[s.sectionCard, isEmpty && { borderColor: '#1a1a1a', opacity: 0.6 }]}
            onPress={() => hasQueue && startSection(sec)}
            activeOpacity={hasQueue ? 0.7 : 1}
          >
            <View style={s.sectionTop}>
              <Text style={s.sectionName}>{sec.section}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                {isEmpty ? (
                  <TouchableOpacity
                    onPress={() => {
                      Alert.alert(
                        'Delete Section',
                        `Delete "${sec.section}"? It has no active inventory.`,
                        [
                          { text: 'Cancel', style: 'cancel' },
                          { text: 'Delete', style: 'destructive', onPress: async () => {
                            try {
                              await api.defragDeleteSection(sec.location_id);
                              loadDashboard();
                            } catch (e) { Alert.alert('Error', e.message); }
                          }},
                        ]
                      );
                    }}
                  >
                    <Text style={{ color: RED, fontSize: 16 }}>🗑</Text>
                  </TouchableOpacity>
                ) : (
                  <Text style={s.sectionPct}>{pct}%</Text>
                )}
              </View>
            </View>
            {!isEmpty && <ProgressBar pct={pct} color={pct === 100 ? GREEN : ACCENT} />}
            <View style={s.sectionStats}>
              <Text style={s.sectionStat}>{sec.total} items</Text>
              {sec.unverified > 0 && (
                <Text style={[s.sectionStat, { color: YELLOW }]}>{sec.unverified} to verify</Text>
              )}
              {sec.missing > 0 && (
                <Text style={[s.sectionStat, { color: RED }]}>{sec.missing} missing</Text>
              )}
              {sec.tier2 > 0 && (
                <Text style={[s.sectionStat, { color: BLUE }]}>T2:{sec.tier2}</Text>
              )}
              {sec.tier3 > 0 && (
                <Text style={[s.sectionStat, { color: PURPLE }]}>T3:{sec.tier3}</Text>
              )}
            </View>
            {hasQueue && (
              <View style={s.sectionActions}>
                <TouchableOpacity
                  style={s.shelfScanBtn}
                  onPress={async () => {
                    const sess = await api.defragStartSession(sec.section).catch(() => ({ session_id: null }));
                    router.push({
                      pathname: '/shelfscan',
                      params: { section: sec.section, sessionId: sess.session_id || '' },
                    });
                  }}
                >
                  <Text style={s.shelfScanBtnText}>📷 Scan Shelf</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.tapThroughBtn}
                  onPress={() => startSection(sec)}
                >
                  <Text style={s.tapThroughBtnText}>Tap-Through</Text>
                </TouchableOpacity>
              </View>
            )}
            {!hasQueue && pct === 100 && !isEmpty && (
              <Text style={[s.sectionStat, { color: GREEN, marginTop: 6 }]}>✓ Complete</Text>
            )}
          </TouchableOpacity>
        );
      })}

    </ScrollView>
  );
}

function ResultStat({ label, value, color }) {
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <Text style={{ color, fontSize: 22, fontWeight: '700' }}>{value}</Text>
      <Text style={{ color: '#555', fontSize: 11 }}>{label}</Text>
    </View>
  );
}

function StatBox({ label, value, color }) {
  return (
    <View style={s.statBox}>
      <Text style={[s.statVal, { color }]}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

// ════════════════════════════════════════════════════════════
// Queue View — card-by-card verification
// ════════════════════════════════════════════════════════════
function QueueView({
  section, queue, cardIndex, queueTotal, queueLoading,
  onFound, onFoundUpdate, onNotFound, onSkip, onExit,
  updateModal, setUpdateModal,
  updateItem, updatePrice, setUpdatePrice,
  updateCondition, setUpdateCondition, onUpdateConfirm,
}) {
  const item    = queue[cardIndex];
  const done    = cardIndex;
  const total   = queueTotal;
  const pct     = total > 0 ? Math.round(done / total * 100) : 0;
  const remaining = total - done;

  if (queueLoading && !item) {
    return (
      <View style={[s.container, { alignItems: 'center', justifyContent: 'center' }]}>
        <ActivityIndicator color={ACCENT} size="large" />
        <Text style={{ color: '#aaa', marginTop: 12 }}>Loading queue…</Text>
      </View>
    );
  }

  if (!item) {
    return (
      <View style={[s.container, { alignItems: 'center', justifyContent: 'center', padding: 32 }]}>
        <Text style={{ color: GREEN, fontSize: 48, marginBottom: 16 }}>✓</Text>
        <Text style={{ color: '#fff', fontSize: 18, fontWeight: '700', marginBottom: 8 }}>
          Section complete
        </Text>
        <Text style={{ color: '#666', textAlign: 'center', marginBottom: 24 }}>
          All items in "{section?.section}" have been reviewed.
        </Text>
        <TouchableOpacity style={s.exitBtn} onPress={onExit}>
          <Text style={s.exitBtnText}>Back to Dashboard</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={s.container}>

      {/* Header */}
      <View style={qv.header}>
        <TouchableOpacity onPress={onExit}>
          <Text style={qv.backBtn}>← Exit</Text>
        </TouchableOpacity>
        <Text style={qv.sectionName}>{section?.section}</Text>
        <Text style={qv.counter}>{done}/{total}</Text>
      </View>

      {/* Progress */}
      <View style={qv.progressRow}>
        <ProgressBar pct={pct} color={ACCENT} />
        <Text style={qv.pctLabel}>{remaining} left</Text>
      </View>

      {/* Card */}
      <ScrollView style={qv.cardScroll} contentContainerStyle={qv.cardContent}>
        <View style={qv.card}>
          <View style={qv.cardTop}>
            <TierBadge tier={item.trust_tier || 1} />
            <Text style={qv.sku}>{item.gibson_sku}</Text>
          </View>

          <Text style={qv.title}>{item.title || '—'}</Text>
          <Text style={qv.author}>{item.author || ''}</Text>

          <View style={qv.metaRow}>
            {item.isbn_13 && <Text style={qv.meta}>ISBN {item.isbn_13}</Text>}
            {item.publication_year && <Text style={qv.meta}>{item.publication_year}</Text>}
            {item.condition_grade && <Text style={qv.meta}>{item.condition_grade}</Text>}
            {item.asking_price && (
              <Text style={[qv.meta, { color: GREEN }]}>${Number(item.asking_price).toFixed(2)}</Text>
            )}
          </View>

          {item.amazon_listing_id && (
            <Text style={qv.sourceTag}>Amazon listing: {item.amazon_listing_id}</Text>
          )}
          {item.kz_status && (
            <Text style={qv.sourceTag}>Ka-Zam: {item.kz_status}</Text>
          )}
        </View>
      </ScrollView>

      {/* Action buttons */}
      <View style={qv.actions}>
        <TouchableOpacity style={[qv.btn, { backgroundColor: GREEN }]} onPress={onFound}>
          <Text style={qv.btnText}>✓ Found</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[qv.btn, { backgroundColor: YELLOW + 'cc' }]} onPress={onFoundUpdate}>
          <Text style={qv.btnText}>Found — Update</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[qv.btn, { backgroundColor: RED }]} onPress={onNotFound}>
          <Text style={qv.btnText}>Not Found</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[qv.btn, { backgroundColor: INACTIVE }]} onPress={onSkip}>
          <Text style={[qv.btnText, { color: '#aaa' }]}>Skip</Text>
        </TouchableOpacity>
      </View>

      {/* Found-Update modal */}
      <Modal visible={updateModal} transparent animationType="slide">
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <Text style={s.modalTitle}>Update & Confirm</Text>
            <Text style={s.modalSub}>{updateItem?.title}</Text>

            <Text style={s.modalLabel}>Price</Text>
            <TextInput
              style={s.modalInput}
              value={updatePrice}
              onChangeText={setUpdatePrice}
              keyboardType="decimal-pad"
              placeholder="0.00"
              placeholderTextColor="#444"
            />

            <Text style={s.modalLabel}>Condition</Text>
            <View style={s.condRow}>
              {['VG+','VG','G+','G','Fair','Poor'].map(c => (
                <TouchableOpacity
                  key={c}
                  style={[s.condChip, updateCondition === c && s.condChipActive]}
                  onPress={() => setUpdateCondition(c)}
                >
                  <Text style={[s.condChipText, updateCondition === c && s.condChipTextActive]}>
                    {c}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <View style={s.modalBtns}>
              <TouchableOpacity style={s.modalCancel} onPress={() => setUpdateModal(false)}>
                <Text style={{ color: '#888' }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.modalConfirm} onPress={onUpdateConfirm}>
                <Text style={{ color: '#fff', fontWeight: '700' }}>Confirm Found</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

    </View>
  );
}

// ════════════════════════════════════════════════════════════
// Missing View
// ════════════════════════════════════════════════════════════
function MissingView({ missing, loading, onResolve, onBack }) {
  return (
    <View style={s.container}>
      <View style={mv.header}>
        <TouchableOpacity onPress={onBack}>
          <Text style={mv.backBtn}>← Back</Text>
        </TouchableOpacity>
        <Text style={mv.title}>Missing Queue ({missing.length})</Text>
      </View>

      {loading ? (
        <ActivityIndicator color={ACCENT} style={{ marginTop: 40 }} />
      ) : missing.length === 0 ? (
        <View style={{ alignItems: 'center', marginTop: 60 }}>
          <Text style={{ color: GREEN, fontSize: 32, marginBottom: 12 }}>✓</Text>
          <Text style={{ color: '#aaa' }}>No missing items</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
          {missing.map(item => (
            <View key={item.stock_item_id} style={mv.card}>
              <Text style={mv.title2}>{item.title || '—'}</Text>
              <Text style={mv.author}>{item.author || ''}</Text>
              <View style={mv.meta}>
                <Text style={mv.metaTxt}>{item.gibson_sku}</Text>
                {item.isbn_13 && <Text style={mv.metaTxt}>{item.isbn_13}</Text>}
                {item.section && <Text style={mv.metaTxt}>{item.section}</Text>}
                {item.asking_price && (
                  <Text style={[mv.metaTxt, { color: GREEN }]}>${Number(item.asking_price).toFixed(2)}</Text>
                )}
                <TierBadge tier={item.trust_tier || 1} />
              </View>
              <View style={mv.resRow}>
                <TouchableOpacity style={[mv.resBtn, { borderColor: GREEN }]}
                  onPress={() => onResolve(item, 'FOUND')}>
                  <Text style={[mv.resTxt, { color: GREEN }]}>Found</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[mv.resBtn, { borderColor: YELLOW }]}
                  onPress={() => onResolve(item, 'SOLD_CONFIRMED')}>
                  <Text style={[mv.resTxt, { color: YELLOW }]}>Sold</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[mv.resBtn, { borderColor: BLUE }]}
                  onPress={() => onResolve(item, 'RELOCATED')}>
                  <Text style={[mv.resTxt, { color: BLUE }]}>Relocated</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[mv.resBtn, { borderColor: '#555' }]}
                  onPress={() => onResolve(item, 'WITHDRAWN')}>
                  <Text style={[mv.resTxt, { color: '#555' }]}>Remove</Text>
                </TouchableOpacity>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}


// ════════════════════════════════════════════════════════════
// Styles
// ════════════════════════════════════════════════════════════
const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  content:   { padding: 16, paddingBottom: 40 },

  statsCard: {
    backgroundColor: CARD, borderRadius: 14,
    padding: 16, marginBottom: 16,
    borderWidth: 1, borderColor: '#1e1e2e',
  },
  statsTitle: { color: '#fff', fontSize: 16, fontWeight: '700', marginBottom: 12 },
  statsRow:   { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 },
  statsPct:   { color: '#aaa', fontSize: 12, width: 36, textAlign: 'right' },
  statsGrid:  { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 12 },
  statBox:    { alignItems: 'center', flex: 1 },
  statVal:    { fontSize: 20, fontWeight: '700' },
  statLabel:  { color: '#444', fontSize: 10, marginTop: 2 },
  tierRow:    { flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap', gap: 4 },
  tierLabel:  { color: '#555', fontSize: 11 },
  tierVal:    { fontSize: 12, fontWeight: '700' },

  actionRow: { flexDirection: 'row', gap: 8, marginBottom: 20, flexWrap: 'wrap' },
  actionBtn: {
    borderWidth: 1, borderRadius: 8,
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: 'transparent',
  },
  actionBtnText: { fontSize: 12, fontWeight: '700' },

  sectionHeader: { color: '#444', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 },
  sectionCard: {
    backgroundColor: CARD, borderRadius: 12,
    padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: '#1e1e2e',
  },
  sectionTop:  { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' },
  sectionName: { color: '#fff', fontSize: 15, fontWeight: '700' },
  sectionPct:  { color: '#666', fontSize: 12 },
  sectionStats:{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 8 },
  sectionStat: { color: '#555', fontSize: 11 },
  sectionActions: { flexDirection: 'row', gap: 8, marginTop: 10 },
  shelfScanBtn: {
    flex: 2, backgroundColor: ACCENT + '22',
    borderWidth: 1, borderColor: ACCENT,
    borderRadius: 8, padding: 9, alignItems: 'center',
  },
  shelfScanBtnText: { color: ACCENT, fontWeight: '700', fontSize: 13 },
  tapThroughBtn: {
    flex: 1, borderWidth: 1, borderColor: '#333',
    borderRadius: 8, padding: 9, alignItems: 'center',
  },
  tapThroughBtnText: { color: '#555', fontWeight: '600', fontSize: 12 },

  exitBtn: {
    backgroundColor: '#1e1e2e', borderRadius: 10,
    paddingHorizontal: 24, paddingVertical: 12,
  },
  exitBtnText: { color: '#fff', fontWeight: '600' },

  // Modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: '#13131f', borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: 24, paddingBottom: 40,
    borderTopWidth: 1, borderColor: '#252535',
  },
  modalTitle: { color: '#fff', fontSize: 16, fontWeight: '700', marginBottom: 4 },
  modalSub:   { color: '#666', fontSize: 13, marginBottom: 16 },
  modalLabel: { color: '#555', fontSize: 12, marginBottom: 4, marginTop: 12 },
  modalInput: {
    backgroundColor: '#1a1a2a', borderWidth: 1, borderColor: '#252535',
    borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10,
    color: '#fff', fontSize: 15,
  },
  condRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  condChip: {
    borderWidth: 1, borderColor: '#333', borderRadius: 16,
    paddingHorizontal: 12, paddingVertical: 6,
  },
  condChipActive: { borderColor: ACCENT, backgroundColor: ACCENT + '22' },
  condChipText: { color: '#555', fontSize: 12 },
  condChipTextActive: { color: ACCENT, fontWeight: '700' },
  modalBtns:    { flexDirection: 'row', gap: 12, marginTop: 20 },
  modalCancel:  { flex: 1, padding: 14, alignItems: 'center', borderRadius: 10, backgroundColor: '#1a1a2a' },
  modalConfirm: { flex: 2, padding: 14, alignItems: 'center', borderRadius: 10, backgroundColor: ACCENT },
});

const imp = StyleSheet.create({
  sourceRow: { flexDirection: 'row', gap: 10, marginBottom: 16 },
  sourceBtn: {
    flex: 1, borderWidth: 1, borderColor: '#333', borderRadius: 10,
    padding: 14, alignItems: 'center',
  },
  sourceTxt: { color: '#555', fontWeight: '700', fontSize: 14 },
  uploadBtn: {
    backgroundColor: ACCENT, borderRadius: 12,
    padding: 16, alignItems: 'center', marginBottom: 20,
  },
  uploadTxt: { color: '#fff', fontWeight: '700', fontSize: 15 },
  resultCard: {
    backgroundColor: CARD, borderRadius: 12, padding: 16,
    borderWidth: 1, borderColor: '#1e1e2e',
  },
  resultTitle: { color: '#fff', fontSize: 15, fontWeight: '700', marginBottom: 12 },
  resultRow: { flexDirection: 'row', justifyContent: 'space-around' },
});

const qv = StyleSheet.create({
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: 56, paddingBottom: 12,
    backgroundColor: BG,
  },
  backBtn:    { color: ACCENT, fontSize: 14 },
  sectionName:{ color: '#fff', fontSize: 14, fontWeight: '700', flex: 1, textAlign: 'center' },
  counter:    { color: '#555', fontSize: 12 },
  progressRow:{ paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  pctLabel:   { color: '#555', fontSize: 11, width: 50, textAlign: 'right' },
  cardScroll: { flex: 1, paddingHorizontal: 16 },
  cardContent:{ paddingBottom: 16 },
  card: {
    backgroundColor: CARD, borderRadius: 14, padding: 20,
    borderWidth: 1, borderColor: '#1e1e2e',
  },
  cardTop:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  sku:       { color: '#444', fontSize: 12 },
  title:     { color: '#fff', fontSize: 18, fontWeight: '700', lineHeight: 24, marginBottom: 6 },
  author:    { color: '#888', fontSize: 14, marginBottom: 14 },
  metaRow:   { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  meta:      { color: '#555', fontSize: 12, backgroundColor: '#1a1a2a', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  sourceTag: { color: '#444', fontSize: 11, marginTop: 10 },
  actions:   { padding: 16, paddingBottom: 36, gap: 10, backgroundColor: 'rgba(13,13,25,0.97)' },
  btn:       { borderRadius: 12, padding: 14, alignItems: 'center' },
  btnText:   { color: '#fff', fontWeight: '700', fontSize: 15 },
});

const mv = StyleSheet.create({
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 16,
    paddingHorizontal: 16, paddingTop: 56, paddingBottom: 16,
    backgroundColor: BG,
  },
  backBtn: { color: ACCENT, fontSize: 14 },
  title:   { color: '#fff', fontSize: 16, fontWeight: '700' },
  card: {
    backgroundColor: CARD, borderRadius: 12, padding: 14,
    borderWidth: 1, borderColor: '#1e1e2e',
  },
  title2:  { color: '#fff', fontSize: 15, fontWeight: '700', marginBottom: 4 },
  author:  { color: '#888', fontSize: 13, marginBottom: 10 },
  meta:    { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12, alignItems: 'center' },
  metaTxt: { color: '#555', fontSize: 11 },
  resRow:  { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  resBtn:  { borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  resTxt:  { fontSize: 11, fontWeight: '700' },
});
