/**
 * Gibson — Research Screen.
 * Correction review queue, ghost books.
 */

import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator } from 'react-native';
import { api } from '../../src/lib/api';

const ACCENT = '#e94560';
const BG = '#0f0f1a';
const CARD = '#13131f';

const CONCERN = {
  HIGH:   { bg: '#2d0f0f', border: '#e74c3c', text: '#e74c3c', label: 'HIGH' },
  MEDIUM: { bg: '#2d1e0a', border: '#f39c12', text: '#f39c12', label: 'MED' },
  LOW:    { bg: '#0d2a15', border: '#2ecc71', text: '#2ecc71', label: 'LOW' },
};

const GHOST_STATUS_COLOR = {
  pending:      '#555',
  researching:  '#3498db',
  resolved:     '#2ecc71',
  unresolvable: '#e74c3c',
};

function ConcernPill({ level }) {
  const c = CONCERN[level] || CONCERN.LOW;
  return (
    <View style={[s.pill, { backgroundColor: c.bg, borderColor: c.border }]}>
      <Text style={[s.pillText, { color: c.text }]}>{c.label}</Text>
    </View>
  );
}

export default function ResearchScreen() {
  const [tab, setTab] = useState('corrections');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadTab(tab); }, [tab]);

  async function loadTab(t) {
    setLoading(true);
    try {
      if (t === 'corrections') {
        const r = await api.get('/api/research/review');
        setItems(r.corrections || r || []);
      } else {
        const r = await api.get('/api/ghostbook/queue');
        setItems(r.items || r || []);
      }
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <View style={s.container}>
      {/* Tabs */}
      <View style={s.tabBar}>
        {[
          { key: 'corrections', label: 'Corrections' },
          { key: 'ghostbook',   label: 'Ghost Books' },
        ].map(({ key, label }) => (
          <TouchableOpacity
            key={key}
            style={[s.tab, tab === key && s.tabActive]}
            onPress={() => setTab(key)}
          >
            <Text style={[s.tabText, tab === key && s.tabTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading
        ? <ActivityIndicator color={ACCENT} style={{ marginTop: 40 }} />
        : (
          <FlatList
            data={items}
            keyExtractor={(item, i) => item.correction_id || item.ghost_book_id || String(i)}
            contentContainerStyle={items.length === 0 ? s.emptyContainer : { padding: 12 }}
            ListEmptyComponent={
              <View style={s.emptyWrap}>
                <Text style={s.emptyIcon}>{tab === 'corrections' ? '✅' : '👻'}</Text>
                <Text style={s.emptyTitle}>Queue is clear</Text>
                <Text style={s.emptyHint}>
                  {tab === 'corrections'
                    ? 'No corrections waiting for review'
                    : 'No ghost books in the queue'}
                </Text>
              </View>
            }
            renderItem={({ item }) => (
              tab === 'corrections'
                ? <CorrectionCard item={item} />
                : <GhostCard item={item} />
            )}
          />
        )
      }
    </View>
  );
}

function CorrectionCard({ item }) {
  return (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <ConcernPill level={item.concern_level} />
        <Text style={s.fieldName}>{item.field_name}</Text>
        <Text style={s.timestamp}>{item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}</Text>
      </View>
      <View style={s.changeBlock}>
        <View style={s.changeLine}>
          <Text style={s.changeDir}>Was</Text>
          <Text style={s.originalVal} numberOfLines={2}>{item.original_value || '—'}</Text>
        </View>
        <View style={s.changeArrow}><Text style={s.changeArrowText}>↓</Text></View>
        <View style={s.changeLine}>
          <Text style={s.changeDir}>Now</Text>
          <Text style={s.correctedVal} numberOfLines={2}>{item.corrected_value || '—'}</Text>
        </View>
      </View>
    </View>
  );
}

function GhostCard({ item }) {
  const statusColor = GHOST_STATUS_COLOR[item.research_status] || '#555';
  return (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <View style={[s.statusPill, { borderColor: statusColor }]}>
          <Text style={[s.statusText, { color: statusColor }]}>
            {item.research_status || 'pending'}
          </Text>
        </View>
      </View>
      <Text style={s.ghostTitle} numberOfLines={2}>
        {item.physical_description || 'Unknown physical description'}
      </Text>
      {item.notes && <Text style={s.ghostNotes} numberOfLines={2}>{item.notes}</Text>}
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },

  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a2a',
    backgroundColor: '#0c0c17',
  },
  tab: { flex: 1, paddingVertical: 14, alignItems: 'center' },
  tabActive: { borderBottomWidth: 2, borderBottomColor: ACCENT },
  tabText: { color: '#444', fontSize: 13, fontWeight: '600' },
  tabTextActive: { color: '#fff' },

  emptyContainer: { flex: 1 },
  emptyWrap: { alignItems: 'center', marginTop: 70 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { color: '#fff', fontSize: 16, fontWeight: '600' },
  emptyHint: { color: '#555', fontSize: 13, marginTop: 6, textAlign: 'center' },

  card: {
    backgroundColor: CARD,
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#1e1e2e',
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
  },
  fieldName: { flex: 1, color: '#888', fontSize: 12 },
  timestamp: { color: '#333', fontSize: 11 },

  pill: {
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: 6, borderWidth: 1,
  },
  pillText: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },

  changeBlock: { gap: 4 },
  changeLine: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  changeDir: { color: '#555', fontSize: 11, width: 28, paddingTop: 1 },
  changeArrow: { paddingLeft: 28 },
  changeArrowText: { color: '#333', fontSize: 12 },
  originalVal: { flex: 1, color: '#777', fontSize: 13 },
  correctedVal: { flex: 1, color: '#fff', fontSize: 13, fontWeight: '600' },

  statusPill: {
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: 6, borderWidth: 1,
  },
  statusText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },

  ghostTitle: { color: '#fff', fontSize: 14, fontWeight: '600' },
  ghostNotes: { color: '#666', fontSize: 12, marginTop: 6 },
});
