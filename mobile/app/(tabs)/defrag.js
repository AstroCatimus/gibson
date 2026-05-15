/**
 * Gibson — Shelf Verification Tab.
 * Walk inventory section by section, card by card.
 * FOUND ✓ | FOUND—UPDATE | NOT FOUND | SKIP
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Modal, TextInput, Alert, Linking,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { api } from '../../src/lib/api';
import { C } from '../../src/lib/theme';

// ─── Tier badge ───────────────────────────────────────────────────
function TierBadge({ tier }) {
  const palette = {
    1: { color: C.green,  label: 'Gibson' },
    2: { color: C.blue,   label: 'Amazon' },
    3: { color: C.purple, label: 'Ka-Zam' },
  };
  const { color, label } = palette[tier] || { color: C.text3, label: 'T?' };
  return (
    <View style={[tb.badge, { borderColor: color, backgroundColor: color + '22' }]}>
      <Text style={[tb.text, { color }]}>T{tier} · {label}</Text>
    </View>
  );
}
const tb = StyleSheet.create({
  badge: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 7, paddingVertical: 2 },
  text:  { fontSize: 10, fontWeight: '700' },
});

// ─── Progress bar ─────────────────────────────────────────────────
function ProgressBar({ pct, color }) {
  const barColor = color || C.accent;
  return (
    <View style={pb.track}>
      <View style={[pb.fill, { width: `${Math.min(100, pct)}%`, backgroundColor: barColor }]} />
    </View>
  );
}
const pb = StyleSheet.create({
  track: { height: 5, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden', flex: 1 },
  fill:  { height: '100%', borderRadius: 3 },
});


// ═══════════════════════════════════════════════════════════════
// Main screen
// ═══════════════════════════════════════════════════════════════
export default function DefragScreen() {
  const [view, setView]           = useState('dashboard');
  const [stats, setStats]         = useState(null);
  const [sections, setSections]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showEmpty, setShowEmpty] = useState(false);

  const [activeSection, setActiveSection]     = useState(null);
  const [sessionId, setSessionId]             = useState(null);
  const [queue, setQueue]                     = useState([]);
  const [queueOffset, setQueueOffset]         = useState(0);
  const [queueTotal, setQueueTotal]           = useState(0);
  const [queueLoading, setQueueLoading]       = useState(false);
  const [cardIndex, setCardIndex]             = useState(0);

  const [updateModal, setUpdateModal]         = useState(false);
  const [updateItem, setUpdateItem]           = useState(null);
  const [updatePrice, setUpdatePrice]         = useState('');
  const [updateCondition, setUpdateCondition] = useState('');

  const [missing, setMissing]               = useState([]);
  const [missingLoading, setMissingLoading] = useState(false);

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

  async function startSection(section) {
    // Show the queue view immediately — load session + first batch in parallel
    setActiveSection(section);
    setCardIndex(0);
    setQueueOffset(0);
    setQueue([]);
    setView('queue');
    try {
      const [sess] = await Promise.all([
        api.defragStartSession(section.section),
        loadQueue(section.section, 0),
      ]);
      setSessionId(sess.session_id);
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

  function verifyAction(action, extras = {}) {
    const item = queue[cardIndex];
    if (!item) return;
    // Advance immediately — never block the UI on a network round-trip.
    // Fire-and-forget; the status update is non-critical in the moment.
    advanceCard();
    api.defragVerify(item.stock_item_id, action, { session_id: sessionId, ...extras })
      .catch(e => console.warn(`verify ${action} failed silently:`, e.message));
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
  const [importJob, setImportJob]         = useState(null);
  const [importLoading, setImportLoading] = useState(false);
  const importPollRef = React.useRef(null);

  function stopPolling() {
    if (importPollRef.current) {
      clearInterval(importPollRef.current);
      importPollRef.current = null;
    }
  }

  // Poll the queue row directly from Supabase — no API needed.
  async function pollQueueStatus(supabaseClient, queueId) {
    try {
      const { data, error } = await supabaseClient
        .from('gibson_import_queue')
        .select('queue_id,status,total,processed,created,skipped,errors,pct,error_details')
        .eq('queue_id', queueId)
        .single();
      if (error || !data) return;

      const done = data.status === 'DONE' || data.status === 'FAILED';
      setImportJob({
        queue_id: data.queue_id,
        status:   data.status === 'DONE' ? 'done'
                : data.status === 'FAILED' ? 'failed'
                : data.status === 'PROCESSING' ? 'running'
                : 'queued',
        done,
        total:         data.total     ?? 0,
        processed:     data.processed ?? 0,
        created:       data.created   ?? 0,
        skipped:       data.skipped   ?? 0,
        errors:        data.errors    ?? 0,
        pct:           data.pct       ?? 0,
        error_details: data.error_details ?? [],
      });
      if (done) {
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
      const storeId = session?.user?.user_metadata?.store_id
                   || process.env.EXPO_PUBLIC_DEFAULT_STORE_ID;

      // ── Step 1: Upload file to Supabase Storage ──────────────
      // Path: {storePrefix}/{timestamp}-{filename}
      const ts        = Date.now();
      const safeName  = (asset.name || 'import.tsv').replace(/[^a-zA-Z0-9._-]/g, '_');
      const storePrefix = storeId?.slice(-4) || 'xx';  // last 4 chars of UUID for readability
      const storagePath = `${storePrefix}/${ts}-${safeName}`;

      setImportJob({ status: 'uploading', pct: 0, done: false });

      // Read file bytes and upload
      const fileResp  = await fetch(asset.uri);
      const buffer    = await fileResp.arrayBuffer();

      const { error: uploadError } = await supabase.storage
        .from('gibson-imports')
        .upload(storagePath, buffer, {
          contentType: asset.mimeType || 'text/tab-separated-values',
          upsert: false,
        });

      if (uploadError) throw new Error(`Upload failed: ${uploadError.message}`);

      // ── Step 2: Insert queue row (direct to Supabase DB) ─────
      // No API needed — mobile writes directly via Supabase client.
      const { data: queueRow, error: insertError } = await supabase
        .from('gibson_import_queue')
        .insert({
          store_id:     storeId,
          source:       source,
          storage_path: storagePath,
          filename:     asset.name || safeName,
          status:       'PENDING',
        })
        .select('queue_id')
        .single();

      if (insertError) throw new Error(`Queue insert failed: ${insertError.message}`);

      // ── Step 3: Poll the queue row directly ──────────────────
      const queueId = queueRow.queue_id;
      setImportJob({ queue_id: queueId, status: 'queued', pct: 0, done: false,
                     total: 0, processed: 0, created: 0, skipped: 0, errors: 0,
                     error_details: [] });
      stopPolling();
      importPollRef.current = setInterval(() => pollQueueStatus(supabase, queueId), 2500);

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
      <ScrollView style={s.container} contentContainerStyle={[s.content, { paddingTop: 16 }]}>
        <TouchableOpacity onPress={() => setView('dashboard')} style={s.backLink}>
          <Ionicons name="arrow-back" size={16} color={C.accent} />
          <Text style={s.backLinkText}>Dashboard</Text>
        </TouchableOpacity>

        <Text style={s.pageTitle}>Import Inventory</Text>
        <Text style={s.pageSubtitle}>
          Upload a CSV or TSV export. The file goes to Supabase — the API processes it whenever it's running. You don't have to stay on this screen.
        </Text>

        <Text style={s.sectionHeader}>Source Format</Text>
        <View style={imp.sourceRow}>
          {[
            { key: 'kazam', label: 'Ka-Zam', color: C.purple },
            { key: 'amazon', label: 'Amazon', color: C.blue },
          ].map(({ key, label, color }) => (
            <TouchableOpacity
              key={key}
              style={[imp.sourceBtn, importSource === key && { borderColor: color, backgroundColor: color + '20' }]}
              onPress={() => setImportSource(key)}
            >
              <Text style={[imp.sourceTxt, importSource === key && { color }]}>{label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={s.pageSubtitle}>
          {importSource === 'kazam'
            ? 'Ka-Zam export: CSV with isbn, title, author, location, price, condition columns.'
            : 'Amazon Seller Central flat-file TSV (Get Report → Active Listings).'}
        </Text>

        <TouchableOpacity
          style={[imp.uploadBtn, importLoading && { opacity: 0.5 }]}
          onPress={() => pickAndImport(importSource)}
          disabled={importLoading}
        >
          {importLoading && (!importJob || importJob.status === 'uploading')
            ? <ActivityIndicator color={C.bg} />
            : <>
                <Ionicons name="cloud-upload-outline" size={18} color={C.bg} />
                <Text style={imp.uploadTxt}>Choose File & Upload</Text>
              </>
          }
        </TouchableOpacity>

        {importJob && (
          <View style={imp.resultCard}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 }}>
              <Text style={imp.resultTitle}>
                {importJob.status === 'uploading' ? 'Uploading…'
                 : importJob.status === 'queued'   ? 'Queued — waiting for API'
                 : importJob.status === 'running'  ? 'Processing…'
                 : importJob.status === 'failed'   ? 'Import Failed'
                 :                                   'Import Complete'}
              </Text>
              {importJob.status !== 'uploading' && importJob.status !== 'queued' && (
                <Text style={{ color: C.text2, fontSize: 13, fontWeight: '700' }}>{importJob.pct ?? 0}%</Text>
              )}
            </View>

            {importJob.status === 'queued' ? (
              <Text style={{ color: C.text3, fontSize: 12, lineHeight: 18 }}>
                File uploaded to Supabase. The API will pick it up automatically — you can close this screen and come back later.
              </Text>
            ) : (
              <>
                <ProgressBar pct={importJob.pct ?? 0}
                  color={importJob.status === 'failed' ? C.red : importJob.done ? C.green : C.accent} />

                <Text style={{ color: C.text3, fontSize: 11, marginTop: 8, marginBottom: 14 }}>
                  {importJob.processed ?? 0} / {importJob.total ?? '?'} rows processed
                </Text>

                <View style={imp.resultRow}>
                  <ResultStat label="Created" value={importJob.created ?? 0} color={C.green} />
                  <ResultStat label="Skipped" value={importJob.skipped ?? 0} color={C.yellow} />
                  <ResultStat label="Errors"  value={importJob.errors  ?? 0} color={C.red} />
                </View>

                {importJob.error_details?.length > 0 && (
                  <>
                    <Text style={{ color: C.red, fontSize: 12, marginTop: 14, marginBottom: 6 }}>First errors:</Text>
                    {importJob.error_details.map((e, i) => (
                      <Text key={i} style={{ color: C.text3, fontSize: 11, marginBottom: 2 }}>
                        Row {e.row}: {e.error}
                      </Text>
                    ))}
                  </>
                )}
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
  const emptySections = sections.filter(sec => sec.total === 0);

  return (
    <ScrollView style={s.container} contentContainerStyle={s.content}>

      {/* Stats card */}
      {loading ? (
        <ActivityIndicator color={C.accent} style={{ marginTop: 40 }} />
      ) : stats ? (
        <View style={s.statsCard}>
          <View style={s.statsHeader}>
            <Text style={s.statsTitle}>Inventory Progress</Text>
            <Text style={s.statsPct}>{stats.pct_complete}%</Text>
          </View>
          <ProgressBar pct={stats.pct_complete} />

          <View style={s.statsGrid}>
            <StatBox label="Total"     value={stats.total}     color={C.text2} />
            <StatBox label="Verified"  value={stats.verified}  color={C.green} />
            <StatBox label="Missing"   value={stats.missing}   color={C.red} />
            <StatBox label="Remaining" value={stats.unverified} color={C.yellow} />
          </View>

          <View style={s.divider} />

          <View style={s.tierRow}>
            <TierItem label="Gibson" value={stats.tier_breakdown.tier1} color={C.green} />
            <TierItem label="Amazon" value={stats.tier_breakdown.tier2} color={C.blue} />
            <TierItem label="Ka-Zam" value={stats.tier_breakdown.tier3} color={C.purple} />
          </View>

          {stats.price_staleness && (
            <>
              <View style={s.divider} />
              <View style={s.tierRow}>
                <TierItem label="Legacy" value={stats.price_staleness.legacy} color={C.yellow} />
                <TierItem label="Stale"  value={stats.price_staleness.stale + stats.price_staleness.aging} color={C.yellow} />
                <TierItem label="Fresh"  value={stats.price_staleness.fresh} color={C.green} />
                {stats.unsectioned > 0 && (
                  <TierItem label="No Section" value={stats.unsectioned} color={C.red} />
                )}
              </View>
            </>
          )}
        </View>
      ) : null}

      {/* Quick actions */}
      <View style={s.actionGrid}>
        <ActionButton
          label="Import Files"
          icon="cloud-upload-outline"
          color={C.accent}
          onPress={() => setView('import')}
        />
        <ActionButton
          label={`Missing${stats?.missing ? ` (${stats.missing})` : ''}`}
          icon="alert-circle-outline"
          color={C.red}
          onPress={openMissing}
        />
        <ActionButton
          label="Amazon TSV"
          icon="download-outline"
          color={C.blue}
          onPress={() => Linking.openURL(api.defragExport('amazon', 'verified'))}
        />
        <ActionButton
          label="Biblio TSV"
          icon="download-outline"
          color={C.purple}
          onPress={() => Linking.openURL(api.defragExport('biblio', 'verified'))}
        />
      </View>

      {/* Section list header */}
      <View style={s.sectionListHeader}>
        <Text style={s.sectionHeader}>Sections</Text>
        <View style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
          {emptySections.length > 0 && (
            <TouchableOpacity
              onPress={() => {
                Alert.alert(
                  'Clean Up Empty Sections',
                  `Delete all ${emptySections.length} sections with no active inventory?`,
                  [
                    { text: 'Cancel', style: 'cancel' },
                    {
                      text: 'Delete All', style: 'destructive',
                      onPress: async () => {
                        try {
                          const r = await api.defragDeleteEmptySections();
                          Alert.alert('Done', `Removed ${r.deleted} empty section${r.deleted !== 1 ? 's' : ''}`);
                          loadDashboard();
                        } catch (e) { Alert.alert('Error', e.message); }
                      },
                    },
                  ]
                );
              }}
            >
              <Text style={{ color: C.red, fontSize: 12, fontWeight: '600' }}>
                Clean up empty
              </Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => setShowEmpty(v => !v)}>
            <Text style={{ color: showEmpty ? C.accent : C.text3, fontSize: 12 }}>
              {showEmpty ? 'Hide empty' : 'Show empty'}
            </Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading ? null : sections
        .filter(sec => showEmpty || sec.total > 0)
        .map((sec) => {
          const pct     = sec.total > 0 ? Math.round(sec.verified / sec.total * 100) : 0;
          const isEmpty = sec.total === 0;
          const hasQueue = sec.unverified > 0;
          return (
            <View
              key={sec.location_id || sec.section}
              style={[s.sectionCard, isEmpty && s.sectionCardEmpty]}
            >
              <View style={s.sectionTop}>
                <Text style={[s.sectionName, isEmpty && { color: C.text3 }]}>{sec.section}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  {isEmpty ? (
                    <TouchableOpacity
                      style={s.trashBtn}
                      onPress={() => {
                        Alert.alert(
                          'Delete Section',
                          `Delete "${sec.section}"? It has no active inventory.`,
                          [
                            { text: 'Cancel', style: 'cancel' },
                            {
                              text: 'Delete', style: 'destructive',
                              onPress: async () => {
                                try {
                                  await api.defragDeleteSection(sec.location_id);
                                  loadDashboard();
                                } catch (e) { Alert.alert('Error', e.message); }
                              },
                            },
                          ]
                        );
                      }}
                    >
                      <Ionicons name="trash-outline" size={16} color={C.red} />
                    </TouchableOpacity>
                  ) : (
                    <Text style={s.sectionPct}>{pct}%</Text>
                  )}
                </View>
              </View>

              {!isEmpty && <ProgressBar pct={pct} color={pct === 100 ? C.green : C.accent} />}

              <View style={s.sectionStats}>
                <Text style={s.sectionStat}>{sec.total} items</Text>
                {sec.unverified > 0 && (
                  <Text style={[s.sectionStat, { color: C.yellow }]}>{sec.unverified} to verify</Text>
                )}
                {sec.missing > 0 && (
                  <Text style={[s.sectionStat, { color: C.red }]}>{sec.missing} missing</Text>
                )}
                {sec.tier2 > 0 && (
                  <Text style={[s.sectionStat, { color: C.blue }]}>T2:{sec.tier2}</Text>
                )}
                {sec.tier3 > 0 && (
                  <Text style={[s.sectionStat, { color: C.purple }]}>T3:{sec.tier3}</Text>
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
                    <Ionicons name="camera-outline" size={15} color={C.accent} />
                    <Text style={s.shelfScanBtnText}>Scan Shelf</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={s.tapThroughBtn} onPress={() => startSection(sec)}>
                    <Text style={s.tapThroughBtnText}>Tap-Through</Text>
                  </TouchableOpacity>
                </View>
              )}
              {!hasQueue && pct === 100 && !isEmpty && (
                <Text style={[s.sectionStat, { color: C.green, marginTop: 6 }]}>✓ Complete</Text>
              )}
            </View>
          );
        })
      }
    </ScrollView>
  );
}

function ResultStat({ label, value, color }) {
  return (
    <View style={{ alignItems: 'center', flex: 1 }}>
      <Text style={{ color, fontSize: 22, fontWeight: '700' }}>{value}</Text>
      <Text style={{ color: C.text3, fontSize: 11, marginTop: 2 }}>{label}</Text>
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

function TierItem({ label, value, color }) {
  return (
    <View style={{ alignItems: 'center' }}>
      <Text style={{ color, fontSize: 14, fontWeight: '700' }}>{value}</Text>
      <Text style={{ color: C.text3, fontSize: 10, marginTop: 1 }}>{label}</Text>
    </View>
  );
}

function ActionButton({ label, icon, color, onPress }) {
  return (
    <TouchableOpacity
      style={[s.actionBtn, { borderColor: color }]}
      onPress={onPress}
      activeOpacity={0.7}
    >
      <Ionicons name={icon} size={16} color={color} />
      <Text style={[s.actionBtnText, { color }]}>{label}</Text>
    </TouchableOpacity>
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
  const item      = queue[cardIndex];
  const done      = cardIndex;
  const total     = queueTotal;
  const pct       = total > 0 ? Math.round(done / total * 100) : 0;
  const remaining = total - done;

  if (queueLoading && !item) {
    return (
      <View style={[s.container, { alignItems: 'center', justifyContent: 'center' }]}>
        <ActivityIndicator color={C.accent} size="large" />
        <Text style={{ color: C.text2, marginTop: 14 }}>Loading queue…</Text>
      </View>
    );
  }

  if (!item) {
    return (
      <View style={[s.container, { alignItems: 'center', justifyContent: 'center', padding: 32 }]}>
        <View style={[s.doneCircle]}>
          <Ionicons name="checkmark" size={40} color={C.green} />
        </View>
        <Text style={{ color: C.text, fontSize: 18, fontWeight: '700', marginBottom: 8 }}>
          Section complete
        </Text>
        <Text style={{ color: C.text2, textAlign: 'center', marginBottom: 28, lineHeight: 20 }}>
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
        <TouchableOpacity onPress={onExit} style={qv.backBtn}>
          <Ionicons name="arrow-back" size={18} color={C.accent} />
        </TouchableOpacity>
        <Text style={qv.sectionName}>{section?.section}</Text>
        <Text style={qv.counter}>{done}/{total}</Text>
      </View>

      {/* Progress */}
      <View style={qv.progressRow}>
        <ProgressBar pct={pct} color={C.accent} />
        <Text style={qv.remaining}>{remaining} left</Text>
      </View>

      {/* Book card */}
      <ScrollView style={qv.cardScroll} contentContainerStyle={qv.cardContent}>
        <View style={qv.card}>
          <View style={qv.cardTop}>
            <TierBadge tier={item.trust_tier || 1} />
            <Text style={qv.sku}>{item.gibson_sku}</Text>
          </View>

          <Text style={qv.title}>{item.title || '—'}</Text>
          <Text style={qv.author}>{item.author || ''}</Text>

          <View style={qv.metaRow}>
            {item.isbn_13 && <View style={qv.metaPill}><Text style={qv.metaText}>ISBN {item.isbn_13}</Text></View>}
            {item.publication_year && <View style={qv.metaPill}><Text style={qv.metaText}>{item.publication_year}</Text></View>}
            {item.condition_grade && <View style={qv.metaPill}><Text style={qv.metaText}>{item.condition_grade}</Text></View>}
            {item.asking_price && (
              <View style={[qv.metaPill, { backgroundColor: C.accentBg, borderColor: C.accent }]}>
                <Text style={[qv.metaText, { color: C.accent, fontWeight: '700' }]}>
                  ${Number(item.asking_price).toFixed(2)}
                </Text>
              </View>
            )}
          </View>

          {item.amazon_listing_id && (
            <Text style={qv.sourceTag}>Amazon: {item.amazon_listing_id}</Text>
          )}
        </View>
      </ScrollView>

      {/* Action buttons */}
      <View style={qv.actions}>
        <View style={qv.actionRow}>
          <TouchableOpacity style={[qv.btn, qv.foundBtn]} onPress={onFound}>
            <Ionicons name="checkmark-circle" size={18} color={C.bg} />
            <Text style={[qv.btnText, { color: C.bg }]}>Found</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[qv.btn, qv.updateBtn]} onPress={onFoundUpdate}>
            <Ionicons name="create-outline" size={18} color={C.yellow} />
            <Text style={[qv.btnText, { color: C.yellow }]}>Found — Update</Text>
          </TouchableOpacity>
        </View>
        <View style={qv.actionRow}>
          <TouchableOpacity style={[qv.btn, qv.notFoundBtn]} onPress={onNotFound}>
            <Ionicons name="close-circle" size={18} color={C.red} />
            <Text style={[qv.btnText, { color: C.red }]}>Not Found</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[qv.btn, qv.skipBtn]} onPress={onSkip}>
            <Ionicons name="arrow-forward-circle-outline" size={18} color={C.text3} />
            <Text style={[qv.btnText, { color: C.text3 }]}>Skip</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Found-Update modal */}
      <Modal visible={updateModal} transparent animationType="slide">
        <View style={s.modalOverlay}>
          <View style={s.modalSheet}>
            <View style={s.sheetHandle} />
            <Text style={s.modalTitle}>Update & Confirm</Text>
            <Text style={s.modalSub}>{updateItem?.title}</Text>

            <Text style={s.modalLabel}>Price</Text>
            <TextInput
              style={s.modalInput}
              value={updatePrice}
              onChangeText={setUpdatePrice}
              keyboardType="decimal-pad"
              placeholder="0.00"
              placeholderTextColor={C.text3}
            />

            <Text style={s.modalLabel}>Condition</Text>
            <View style={s.condRow}>
              {['VG+', 'VG', 'G+', 'G', 'Fair', 'Poor'].map(c => (
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
                <Text style={{ color: C.text2, fontWeight: '600' }}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.modalConfirm} onPress={onUpdateConfirm}>
                <Text style={{ color: C.bg, fontWeight: '700' }}>Confirm Found</Text>
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
        <TouchableOpacity onPress={onBack} style={mv.backBtn}>
          <Ionicons name="arrow-back" size={18} color={C.accent} />
        </TouchableOpacity>
        <Text style={mv.title}>Missing Queue ({missing.length})</Text>
      </View>

      {loading ? (
        <ActivityIndicator color={C.accent} style={{ marginTop: 40 }} />
      ) : missing.length === 0 ? (
        <View style={{ alignItems: 'center', marginTop: 64 }}>
          <Ionicons name="checkmark-circle" size={48} color={C.green} style={{ marginBottom: 12 }} />
          <Text style={{ color: C.text2, fontSize: 15 }}>No missing items</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
          {missing.map(item => (
            <View key={item.stock_item_id} style={mv.card}>
              <Text style={mv.itemTitle}>{item.title || '—'}</Text>
              <Text style={mv.itemAuthor}>{item.author || ''}</Text>
              <View style={mv.meta}>
                <Text style={mv.metaTxt}>{item.gibson_sku}</Text>
                {item.isbn_13 && <Text style={mv.metaTxt}>{item.isbn_13}</Text>}
                {item.section && <Text style={mv.metaTxt}>{item.section}</Text>}
                {item.asking_price && (
                  <Text style={[mv.metaTxt, { color: C.accent }]}>${Number(item.asking_price).toFixed(2)}</Text>
                )}
                <TierBadge tier={item.trust_tier || 1} />
              </View>
              <View style={mv.resRow}>
                {[
                  { label: 'Found',     action: 'FOUND',            color: C.green },
                  { label: 'Sold',      action: 'SOLD_CONFIRMED',   color: C.yellow },
                  { label: 'Relocated', action: 'RELOCATED',        color: C.blue },
                  { label: 'Remove',    action: 'WITHDRAWN',        color: C.text3 },
                ].map(({ label, action, color }) => (
                  <TouchableOpacity
                    key={action}
                    style={[mv.resBtn, { borderColor: color }]}
                    onPress={() => onResolve(item, action)}
                  >
                    <Text style={[mv.resTxt, { color }]}>{label}</Text>
                  </TouchableOpacity>
                ))}
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
  container: { flex: 1, backgroundColor: C.bg },
  content:   { padding: 16, paddingBottom: 48 },

  backLink: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 20 },
  backLinkText: { color: C.accent, fontSize: 14 },
  pageTitle:    { color: C.text, fontSize: 20, fontWeight: '700', marginBottom: 6 },
  pageSubtitle: { color: C.text2, fontSize: 13, lineHeight: 20, marginBottom: 16 },

  // Stats card
  statsCard: {
    backgroundColor: C.card, borderRadius: 14,
    padding: 16, marginBottom: 16,
    borderWidth: 1, borderColor: C.border,
  },
  statsHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 },
  statsTitle:  { color: C.text, fontSize: 15, fontWeight: '700' },
  statsPct:    { color: C.accent, fontSize: 18, fontWeight: '800' },
  statsGrid:   { flexDirection: 'row', justifyContent: 'space-between', marginTop: 14, marginBottom: 4 },
  statBox:     { alignItems: 'center', flex: 1 },
  statVal:     { fontSize: 20, fontWeight: '700' },
  statLabel:   { color: C.text3, fontSize: 10, marginTop: 3, textTransform: 'uppercase', letterSpacing: 0.4 },
  divider:     { height: 1, backgroundColor: C.border, marginVertical: 12 },
  tierRow:     { flexDirection: 'row', justifyContent: 'space-around' },

  // Action grid
  actionGrid:  { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 20 },
  actionBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    borderWidth: 1, borderRadius: 8,
    paddingHorizontal: 12, paddingVertical: 9,
  },
  actionBtnText: { fontSize: 12, fontWeight: '700' },

  // Section list
  sectionListHeader: {
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between', marginBottom: 10,
  },
  sectionHeader: {
    color: C.text3, fontSize: 11,
    textTransform: 'uppercase', letterSpacing: 0.8,
  },
  sectionCard: {
    backgroundColor: C.card, borderRadius: 12,
    padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: C.border,
  },
  sectionCardEmpty: { opacity: 0.55 },
  sectionTop:  { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' },
  sectionName: { color: C.text, fontSize: 15, fontWeight: '600' },
  sectionPct:  { color: C.text3, fontSize: 12 },
  sectionStats:{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 8 },
  sectionStat: { color: C.text3, fontSize: 11 },
  sectionActions: { flexDirection: 'row', gap: 8, marginTop: 10 },
  trashBtn: { padding: 4 },
  shelfScanBtn: {
    flex: 2, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: C.accentBg, borderWidth: 1, borderColor: C.accent,
    borderRadius: 8, padding: 9,
  },
  shelfScanBtnText: { color: C.accent, fontWeight: '700', fontSize: 13 },
  tapThroughBtn: {
    flex: 1, borderWidth: 1, borderColor: C.border,
    borderRadius: 8, padding: 9, alignItems: 'center',
  },
  tapThroughBtnText: { color: C.text2, fontWeight: '600', fontSize: 12 },

  // Completion circle
  doneCircle: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: C.greenBg, borderWidth: 2, borderColor: C.green,
    alignItems: 'center', justifyContent: 'center', marginBottom: 20,
  },
  exitBtn: {
    backgroundColor: C.surface, borderRadius: 10,
    paddingHorizontal: 24, paddingVertical: 12,
    borderWidth: 1, borderColor: C.border,
  },
  exitBtnText: { color: C.text, fontWeight: '600', fontSize: 14 },

  // Modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: C.card, borderTopLeftRadius: 24, borderTopRightRadius: 24,
    padding: 24, paddingBottom: 48,
    borderTopWidth: 1, borderColor: C.border,
  },
  sheetHandle: {
    width: 36, height: 4, borderRadius: 2,
    backgroundColor: C.border, alignSelf: 'center', marginBottom: 20,
  },
  modalTitle:  { color: C.text, fontSize: 16, fontWeight: '700', marginBottom: 4 },
  modalSub:    { color: C.text2, fontSize: 13, marginBottom: 16 },
  modalLabel:  { color: C.text3, fontSize: 12, marginBottom: 6, marginTop: 14, textTransform: 'uppercase', letterSpacing: 0.5 },
  modalInput: {
    backgroundColor: C.surface, borderWidth: 1, borderColor: C.border,
    borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10,
    color: C.text, fontSize: 15,
  },
  condRow:     { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  condChip: {
    borderWidth: 1, borderColor: C.border, borderRadius: 16,
    paddingHorizontal: 12, paddingVertical: 6, backgroundColor: C.surface,
  },
  condChipActive:     { borderColor: C.accent, backgroundColor: C.accentBg },
  condChipText:       { color: C.text3, fontSize: 12 },
  condChipTextActive: { color: C.accent, fontWeight: '700' },
  modalBtns:    { flexDirection: 'row', gap: 10, marginTop: 22 },
  modalCancel:  { flex: 1, padding: 14, alignItems: 'center', borderRadius: 10, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border },
  modalConfirm: { flex: 2, padding: 14, alignItems: 'center', borderRadius: 10, backgroundColor: C.accent },
});

const imp = StyleSheet.create({
  sourceRow: { flexDirection: 'row', gap: 10, marginBottom: 16 },
  sourceBtn: {
    flex: 1, borderWidth: 1, borderColor: C.border, borderRadius: 10,
    padding: 14, alignItems: 'center', backgroundColor: C.surface,
  },
  sourceTxt: { color: C.text3, fontWeight: '700', fontSize: 14 },
  uploadBtn: {
    backgroundColor: C.accent, borderRadius: 12,
    padding: 15, alignItems: 'center', marginBottom: 20,
    flexDirection: 'row', justifyContent: 'center', gap: 8,
  },
  uploadTxt: { color: C.bg, fontWeight: '700', fontSize: 15 },
  resultCard: {
    backgroundColor: C.card, borderRadius: 12, padding: 16,
    borderWidth: 1, borderColor: C.border,
  },
  resultTitle: { color: C.text, fontSize: 15, fontWeight: '700' },
  resultRow: { flexDirection: 'row', justifyContent: 'space-around' },
});

const qv = StyleSheet.create({
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: 56, paddingBottom: 12,
    backgroundColor: C.surface, borderBottomWidth: 1, borderBottomColor: C.border,
  },
  backBtn:    { padding: 4 },
  sectionName:{ color: C.text, fontSize: 14, fontWeight: '700', flex: 1, textAlign: 'center' },
  counter:    { color: C.text3, fontSize: 12 },
  progressRow:{ paddingHorizontal: 16, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 10 },
  remaining:  { color: C.text3, fontSize: 11, width: 48, textAlign: 'right' },
  cardScroll: { flex: 1, paddingHorizontal: 16 },
  cardContent:{ paddingVertical: 12 },
  card: {
    backgroundColor: C.card, borderRadius: 14, padding: 20,
    borderWidth: 1, borderColor: C.border,
  },
  cardTop:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  sku:      { color: C.text3, fontSize: 11, fontFamily: 'monospace' },
  title:    { color: C.text, fontSize: 18, fontWeight: '700', lineHeight: 25, marginBottom: 6 },
  author:   { color: C.text2, fontSize: 14, marginBottom: 16 },
  metaRow:  { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metaPill: {
    backgroundColor: C.surface, borderRadius: 6, borderWidth: 1, borderColor: C.border,
    paddingHorizontal: 8, paddingVertical: 3,
  },
  metaText: { color: C.text2, fontSize: 12 },
  sourceTag:{ color: C.text3, fontSize: 11, marginTop: 12 },

  actions: { padding: 14, paddingBottom: 32, gap: 8, backgroundColor: C.surface, borderTopWidth: 1, borderTopColor: C.border },
  actionRow: { flexDirection: 'row', gap: 8 },
  btn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, borderRadius: 12, padding: 13, borderWidth: 1,
  },
  foundBtn:    { backgroundColor: C.greenBg,  borderColor: C.green },
  updateBtn:   { backgroundColor: C.yellowBg, borderColor: C.yellow },
  notFoundBtn: { backgroundColor: C.redBg,    borderColor: C.red },
  skipBtn:     { backgroundColor: C.surface,  borderColor: C.border },
  btnText:     { fontWeight: '700', fontSize: 14 },
});

const mv = StyleSheet.create({
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 16, paddingTop: 56, paddingBottom: 16,
    backgroundColor: C.surface, borderBottomWidth: 1, borderBottomColor: C.border,
  },
  backBtn: { padding: 4 },
  title:   { color: C.text, fontSize: 16, fontWeight: '700' },
  card: {
    backgroundColor: C.card, borderRadius: 12, padding: 14,
    borderWidth: 1, borderColor: C.border,
  },
  itemTitle:  { color: C.text, fontSize: 15, fontWeight: '600', marginBottom: 3 },
  itemAuthor: { color: C.text2, fontSize: 13, marginBottom: 10 },
  meta:    { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12, alignItems: 'center' },
  metaTxt: { color: C.text3, fontSize: 11 },
  resRow:  { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  resBtn:  { borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  resTxt:  { fontSize: 11, fontWeight: '700' },
});
