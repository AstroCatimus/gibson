/**
 * Gibson — Review Queue Screen.
 * Correction review queue and ghost books.
 */

import { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../../src/lib/api';
import { C } from '../../src/lib/theme';

const CONCERN = {
  HIGH:   { bg: C.redBg,    border: C.red,    text: C.red,    label: 'High' },
  MEDIUM: { bg: C.yellowBg, border: C.yellow, text: C.yellow, label: 'Med' },
  LOW:    { bg: C.greenBg,  border: C.green,  text: C.green,  label: 'Low' },
};

const GHOST_STATUS = {
  pending:      { color: C.text3,  label: 'Pending' },
  researching:  { color: C.blue,   label: 'Researching' },
  resolved:     { color: C.green,  label: 'Resolved' },
  unresolvable: { color: C.red,    label: 'Unresolvable' },
};

const TABS = [
  { key: 'corrections', label: 'Corrections', icon: 'git-compare-outline' },
  { key: 'ghostbook',   label: 'Ghost Books',  icon: 'help-circle-outline' },
];

export default function ResearchScreen() {
  const [tab, setTab]       = useState('corrections');
  const [items, setItems]   = useState([]);
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

      {/* ── Tab switcher ── */}
      <View style={s.tabBar}>
        {TABS.map(({ key, label, icon }) => {
          const active = tab === key;
          return (
            <TouchableOpacity
              key={key}
              style={[s.tab, active && s.tabActive]}
              onPress={() => setTab(key)}
              activeOpacity={0.7}
            >
              <Ionicons
                name={icon}
                size={15}
                color={active ? C.accent : C.text3}
                style={{ marginRight: 6 }}
              />
              <Text style={[s.tabText, active && s.tabTextActive]}>{label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {loading
        ? <ActivityIndicator color={C.accent} style={{ marginTop: 48 }} />
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
  const c = CONCERN[item.concern_level] || CONCERN.LOW;
  return (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <View style={[s.pill, { backgroundColor: c.bg, borderColor: c.border }]}>
          <Text style={[s.pillText, { color: c.text }]}>{c.label}</Text>
        </View>
        <Text style={s.fieldName}>{item.field_name}</Text>
        <Text style={s.timestamp}>
          {item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}
        </Text>
      </View>

      <View style={s.changeBlock}>
        <View style={s.changeLine}>
          <Text style={s.changeDir}>Was</Text>
          <Text style={s.originalVal} numberOfLines={2}>{item.original_value || '—'}</Text>
        </View>
        <View style={s.changeArrowRow}>
          <Ionicons name="arrow-down" size={12} color={C.text3} style={{ marginLeft: 32 }} />
        </View>
        <View style={s.changeLine}>
          <Text style={s.changeDir}>Now</Text>
          <Text style={s.correctedVal} numberOfLines={2}>{item.corrected_value || '—'}</Text>
        </View>
      </View>
    </View>
  );
}

function GhostCard({ item }) {
  const gs = GHOST_STATUS[item.research_status] || GHOST_STATUS.pending;
  return (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <View style={[s.pill, { borderColor: gs.color, backgroundColor: gs.color + '18' }]}>
          <Text style={[s.pillText, { color: gs.color }]}>{gs.label}</Text>
        </View>
      </View>
      <Text style={s.ghostTitle} numberOfLines={2}>
        {item.physical_description || 'Unknown physical description'}
      </Text>
      {item.notes ? (
        <Text style={s.ghostNotes} numberOfLines={2}>{item.notes}</Text>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: C.bg },

  // Tab bar
  tabBar: {
    flexDirection: 'row', backgroundColor: C.surface,
    borderBottomWidth: 1, borderBottomColor: C.border,
    paddingHorizontal: 8,
  },
  tab: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 14, gap: 4, borderBottomWidth: 2, borderBottomColor: 'transparent',
  },
  tabActive:     { borderBottomColor: C.accent },
  tabText:       { color: C.text3, fontSize: 13, fontWeight: '600' },
  tabTextActive: { color: C.text },

  // Empty state
  emptyContainer: { flex: 1 },
  emptyWrap: { alignItems: 'center', marginTop: 72, paddingHorizontal: 40 },
  emptyIcon:  { fontSize: 48, marginBottom: 12 },
  emptyTitle: { color: C.text, fontSize: 16, fontWeight: '600' },
  emptyHint:  { color: C.text2, fontSize: 13, marginTop: 6, textAlign: 'center', lineHeight: 20 },

  // Cards
  card: {
    backgroundColor: C.card, borderRadius: 12,
    padding: 14, marginBottom: 10,
    borderWidth: 1, borderColor: C.border,
  },
  cardHeader: {
    flexDirection: 'row', alignItems: 'center',
    gap: 8, marginBottom: 12,
  },
  fieldName:  { flex: 1, color: C.text2, fontSize: 12 },
  timestamp:  { color: C.text3, fontSize: 11 },

  pill: {
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: 6, borderWidth: 1,
  },
  pillText: { fontSize: 10, fontWeight: '700', letterSpacing: 0.4 },

  // Correction card
  changeBlock: { gap: 2 },
  changeLine:  { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  changeArrowRow: { paddingVertical: 2 },
  changeDir:   { color: C.text3, fontSize: 11, width: 28, paddingTop: 1 },
  originalVal: { flex: 1, color: C.text2, fontSize: 13 },
  correctedVal:{ flex: 1, color: C.text, fontSize: 13, fontWeight: '600' },

  // Ghost card
  ghostTitle: { color: C.text, fontSize: 14, fontWeight: '600' },
  ghostNotes: { color: C.text2, fontSize: 12, marginTop: 6, lineHeight: 18 },
});
